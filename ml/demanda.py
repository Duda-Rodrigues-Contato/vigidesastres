"""Previsão de DEMANDA: quantos atendimentos reativos cada distrito deve ter na PRÓXIMA semana.

Para planejar equipe (escalas, férias, estoque de lonas), não para alertar.

Alvo: soma semanal de atendimentos REATIVOS por distrito (gold.ml_distrito_dia, 2015-2024).
Momento da previsão: segunda-feira de manhã. Só entra o que já se sabe nessa hora: calendário,
feriados da semana, chuva e atendimentos até o domingo anterior. A chuva da própria semana
NÃO entra (a 1ª rodada usava; isso deixava o resultado otimista, porque ninguém sabe na
segunda quanto vai chover até domingo). A versão 0 continua no relatório só para comparação.

Versões (cada uma acrescenta algo à anterior):
  0 original: calendário + chuva da própria semana e da anterior (não usável na prática)
  1 corrigida: calendário + chuva da semana anterior
  2 + demanda das semanas anteriores (semana passada e média das últimas 4)
  3 + chuva detalhada (maior chuva de um dia, dias com 30 mm ou mais, acumulado de 2 e 4 semanas)
  4 + dois modelos: atendimentos ligados à chuva e os demais (vistorias etc.), somados no fim

Modelo: XGBoost com objetivo de CONTAGEM (Poisson).
Régua: a média daquela semana do ano naquele distrito nos anos de treino (o "normal").

Regras fixadas ANTES de rodar:
  - a versão final é escolhida entre 1-4 pelo erro da validação cruzada NO TREINO
    (TimeSeriesSplit), nunca pelo teste;
  - ela é aprovada se errar pelo menos 10% menos que a régua (MAE) no teste 2022-2024.
O teste das outras versões aparece só para mostrar quanto cada mudança ajudou.

Uso:
    python -m ml.demanda
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from xgboost import XGBRegressor

from dominio.feriados import feriados_recife
from etl.destinos import obter_destino

SAIDA = Path(__file__).resolve().parents[1] / "analises" / "ml" / "saida"
TREINO, TESTE = range(2015, 2022), range(2022, 2025)
GRADE = {"n_estimators": [200, 400], "max_depth": [3, 5], "learning_rate": [0.05, 0.1]}
GANHO_MINIMO = 0.10
CHUVA_FORTE_MM = 30

CALENDARIO = ["distrito_codigo", "semana", "mes", "feriados"]
DEMANDA_ANTERIOR = ["atend_ant_1", "atend_media_4"]
CHUVA_DETALHADA = ["chuva_max_dia_ant_mm", "dias_chuva_forte_ant", "chuva_2sem_mm", "chuva_4sem_mm"]
POR_TIPO_ANTERIOR = ["chuva_ant_1", "chuva_media_4", "outros_ant_1", "outros_media_4"]

ORIGINAL = "0 original (chuva da própria semana)"
VERSOES = {
    ORIGINAL: (CALENDARIO + ["chuva_semana_mm", "chuva_semana_anterior_mm"], ["atendimentos"]),
    "1 corrigida": (CALENDARIO + ["chuva_semana_anterior_mm"], ["atendimentos"]),
    "2 + demanda anterior": (CALENDARIO + ["chuva_semana_anterior_mm"] + DEMANDA_ANTERIOR, ["atendimentos"]),
    "3 + chuva detalhada": (CALENDARIO + ["chuva_semana_anterior_mm"] + DEMANDA_ANTERIOR + CHUVA_DETALHADA,
                            ["atendimentos"]),
    "4 + chuva e outros separados": (CALENDARIO + ["chuva_semana_anterior_mm"] + DEMANDA_ANTERIOR + CHUVA_DETALHADA
                                     + POR_TIPO_ANTERIOR, ["atend_chuva", "atend_outros"]),
}
ENTRADAS = VERSOES["1 corrigida"][0]          # compatibilidade com quem importava ENTRADAS


def _anterior(s, coluna, semanas):
    """Valor de `semanas` semanas atrás no mesmo distrito; vazio se houver buraco na série."""
    valores = s.set_index(["distrito_codigo", "inicio"])[coluna]
    chave = pd.MultiIndex.from_arrays([s["distrito_codigo"], s["inicio"] - pd.Timedelta(days=7 * semanas)])
    return pd.Series(valores.reindex(chave).to_numpy(), index=s.index)


def semanal(df):
    """Tabela distrito x dia -> distrito x semana (segunda a domingo) com as entradas de cada versão."""
    df = df.copy()
    df["data"] = pd.to_datetime(df["data"])
    if "atendimentos_chuva" not in df:
        df["atendimentos_chuva"] = 0
    df["inicio"] = df["data"] - pd.to_timedelta(df["data"].dt.day_of_week, unit="D")
    feriados = set()
    for ano in range(df["data"].dt.year.min(), df["data"].dt.year.max() + 1):
        feriados |= {pd.Timestamp(d) for d in feriados_recife(ano)}
    df["feriado"] = df["data"].isin(feriados)
    df["chuva_forte"] = df["chuva_dia_mm"] >= CHUVA_FORTE_MM
    s = df.groupby(["distrito_codigo", "inicio"]).agg(
        atendimentos=("atendimentos_reativos", "sum"), atend_chuva=("atendimentos_chuva", "sum"),
        chuva_semana_mm=("chuva_dia_mm", "sum"), chuva_max_dia_mm=("chuva_dia_mm", "max"),
        dias_chuva_forte=("chuva_forte", "sum"), feriados=("feriado", "sum"),
        dias=("data", "size")).reset_index()
    s = s[s["dias"] == 7].sort_values(["distrito_codigo", "inicio"]).reset_index(drop=True)
    s["atend_chuva"] = s["atend_chuva"].clip(upper=s["atendimentos"])
    s["atend_outros"] = s["atendimentos"] - s["atend_chuva"]

    s["chuva_semana_anterior_mm"] = _anterior(s, "chuva_semana_mm", 1)
    s["chuva_max_dia_ant_mm"] = _anterior(s, "chuva_max_dia_mm", 1)
    s["dias_chuva_forte_ant"] = _anterior(s, "dias_chuva_forte", 1)
    chuva = [_anterior(s, "chuva_semana_mm", k) for k in range(1, 5)]
    s["chuva_2sem_mm"] = pd.concat(chuva[:2], axis=1).sum(axis=1, skipna=False)
    s["chuva_4sem_mm"] = pd.concat(chuva, axis=1).sum(axis=1, skipna=False)
    for coluna, nome in (("atendimentos", "atend"), ("atend_chuva", "chuva"), ("atend_outros", "outros")):
        anteriores = [_anterior(s, coluna, k) for k in range(1, 5)]
        s[f"{nome}_ant_1"] = anteriores[0]
        s[f"{nome}_media_4"] = pd.concat(anteriores, axis=1).mean(axis=1)

    s["semana"] = s["inicio"].dt.isocalendar().week.astype(int).clip(upper=52)
    s["mes"] = s["inicio"].dt.month
    s["ano"] = s["inicio"].dt.year
    return s


def regua(treino, teste):
    """O 'normal': média daquela semana do ano naquele distrito, nos anos de treino."""
    normal = treino.groupby(["distrito_codigo", "semana"])["atendimentos"].mean()
    return teste.set_index(["distrito_codigo", "semana"]).index.map(normal).to_numpy(dtype=float)


def metricas(previsto, real):
    ok = ~np.isnan(previsto)
    p, r = previsto[ok], real[ok]
    mae = float(np.mean(np.abs(p - r)))
    wape = float(np.sum(np.abs(p - r)) / np.sum(r))
    r2 = float(1 - np.sum((r - p) ** 2) / np.sum((r - r.mean()) ** 2))
    return {"mae": mae, "wape": wape, "r2": r2}


def _ajustar(treino, entradas, alvo, grade):
    busca = GridSearchCV(XGBRegressor(objective="count:poisson", tree_method="hist", random_state=42, n_jobs=-1),
                         grade, scoring="neg_mean_absolute_error", cv=TimeSeriesSplit(4), n_jobs=1)
    busca.fit(treino[entradas].astype(float), treino[alvo])
    return busca.best_estimator_


def _versao(treino, teste, entradas, alvos, grade):
    """Treina um modelo por alvo (a demanda é a soma deles); devolve previsão no teste,
    erro da validação cruzada no treino e os modelos."""
    modelos = [_ajustar(treino, entradas, a, grade) for a in alvos]
    previsto = sum(m.predict(teste[entradas].astype(float)) for m in modelos)
    erros = []
    for i_tr, i_va in TimeSeriesSplit(4).split(treino):
        tr, va = treino.iloc[i_tr], treino.iloc[i_va]
        p = sum(clone(m).fit(tr[entradas].astype(float), tr[a]).predict(va[entradas].astype(float))
                for m, a in zip(modelos, alvos))
        erros.append(np.mean(np.abs(p - va["atendimentos"].to_numpy(dtype=float))))
    return previsto, float(np.mean(erros)), modelos


def executar(s, grade=None, avisar=print):
    grade = grade or GRADE
    treino = s[s["ano"].isin(TREINO)].sort_values("inicio")
    teste = s[s["ano"].isin(TESTE)].sort_values("inicio")
    real = teste["atendimentos"].to_numpy(dtype=float)
    normal = regua(treino, teste)
    ref = metricas(normal, real)
    ingenuo = metricas(teste["atend_ant_1"].to_numpy(dtype=float), real)
    avisar(f"treino {len(treino)} distrito-semanas (2015-2021) | teste {len(teste)} (2022-2024)")
    avisar(f"{'versão':38s} {'valid.':>7s} | {'MAE':>6s} {'WAPE':>6s} {'R²':>6s} {'vs régua':>9s}")

    resultados = {}
    for nome, (entradas, alvos) in VERSOES.items():
        previsto, erro_cv, modelos = _versao(treino, teste, entradas, alvos, grade)
        m = metricas(previsto, real)
        resultados[nome] = (previsto, erro_cv, modelos, m)
        avisar(f"{nome:38s} {erro_cv:7.1f} | {m['mae']:6.1f} {m['wape']:6.0%} {m['r2']:6.2f} "
               f"{1 - m['mae'] / ref['mae']:+9.0%}")
    avisar(f"{'régua (o normal)':38s} {'':7s} | {ref['mae']:6.1f} {ref['wape']:6.0%} {ref['r2']:6.2f}")
    avisar(f"{'ingênuo (igual à semana passada)':38s} {'':7s} | {ingenuo['mae']:6.1f} {ingenuo['wape']:6.0%} "
           f"{ingenuo['r2']:6.2f}")
    avisar("(valid. = erro na validação cruzada do treino, usado para escolher; MAE/WAPE/R² = teste)")

    escolhida = min((n for n in resultados if n != ORIGINAL), key=lambda n: resultados[n][1])
    previsto, _, modelos, m = resultados[escolhida]
    aprovado = m["mae"] <= (1 - GANHO_MINIMO) * ref["mae"]
    avisar(f"\nEscolhida pela validação: {escolhida}")
    avisar("Por distrito (teste):")
    for d, g in teste.assign(prev=previsto, normal=normal).groupby("distrito_codigo"):
        avisar(f"  DS {d}: real {g['atendimentos'].mean():6.1f}/semana | erro modelo "
               f"{np.mean(np.abs(g['prev'] - g['atendimentos'])):5.1f} | erro régua "
               f"{np.nanmean(np.abs(g['normal'] - g['atendimentos'])):5.1f}")
    entradas, alvos = VERSOES[escolhida]
    for modelo, alvo in zip(modelos, alvos):
        imp = sorted(zip(entradas, modelo.feature_importances_), key=lambda p: -p[1])[:6]
        avisar(f"Importância ({alvo}): " + ", ".join(f"{k} {v:.2f}" for k, v in imp))
    avisar(f"VEREDITO: {'APROVADO' if aprovado else 'NÃO APROVADO'} (precisa errar pelo menos "
           f"{GANHO_MINIMO:.0%} menos que a régua)")
    return aprovado, m["mae"], ref["mae"]


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    banco = obter_destino().banco
    df = pd.DataFrame(list(banco["gold_ml_distrito_dia"].find(
        {"ano": {"$gte": 2015, "$lte": 2024}},
        {"_id": 0, "distrito_codigo": 1, "data": 1, "atendimentos_reativos": 1, "atendimentos_chuva": 1,
         "chuva_dia_mm": 1})))
    linhas = []
    executar(semanal(df), avisar=lambda t: (print(t, flush=True), linhas.append(t)))
    (SAIDA / "resultado_demanda.txt").write_text("\n".join(linhas), encoding="utf-8")


if __name__ == "__main__":
    main()
