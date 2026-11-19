"""Dengue com clima: temperatura e umidade ajudam a prever os casos de daqui a 4 semanas?

A etapa 4c mostrou que a chuva sozinha não explica a dengue além do ciclo anual. O
mosquito depende principalmente da TEMPERATURA (acelera o ciclo) e da UMIDADE. Aqui o
modelo prevê os casos estimados (InfoDengue) da semana t+4, sabendo o que se sabe na
semana t: os casos das últimas semanas e o clima das últimas 8 semanas.

  com clima   casos recentes + temperatura, umidade e chuva (médias de 4 e 8 semanas)
  sem clima   só os casos recentes (o "controle": a epidemia pela própria inércia)

Clima: ERA5-Land, média dos 8 distritos do Recife; chuva: tabela do modelo de risco.
Treino 2014-2021 | teste 2022-2024 (2025 em diante: o ERA5-Land por unidade não cobre tudo).

Regra fixada ANTES de rodar: o clima ajuda se o erro (MAE do log dos casos) com clima for
pelo menos 5% menor que sem clima, no teste.

Uso:
    python -m ml.dengue_clima
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from xgboost import XGBRegressor

from etl.destinos import obter_destino

SAIDA = Path(__file__).resolve().parents[1] / "analises" / "ml" / "saida"
HORIZONTE = 4
TREINO, TESTE = range(2014, 2022), range(2022, 2025)
CASOS = ["log_casos", "log_casos_1", "log_casos_2", "log_casos_4", "semana_sen", "semana_cos"]
CLIMA = ["temp_4s", "temp_8s", "umidade_4s", "umidade_8s", "chuva_4s", "chuva_8s"]
GRADE = {"n_estimators": [200, 400], "max_depth": [2, 3], "learning_rate": [0.05, 0.1]}
GANHO_MINIMO = 0.05


def montar(dengue, clima, chuva):
    """dengue [{inicio_semana, casos_est}], clima/chuva diários -> uma linha por semana com o alvo t+4."""
    s = dengue.sort_values("inicio_semana").reset_index(drop=True)
    s["inicio_semana"] = pd.to_datetime(s["inicio_semana"])
    for nome, serie, col in (("temp", clima, "temp_media_c"), ("umidade", clima, "umidade_ar_pct"),
                             ("chuva", chuva, "chuva_dia_mm")):
        d = serie.copy()
        d["data"] = pd.to_datetime(d["data"])
        diario = d.groupby("data")[col].mean()
        s[nome] = [diario.loc[i:i + pd.Timedelta(days=6)].mean() for i in s["inicio_semana"]]
    s["log_casos"] = np.log1p(s["casos_est"])
    for k in (1, 2, 4):
        s[f"log_casos_{k}"] = s["log_casos"].shift(k)
    for nome in ("temp", "umidade", "chuva"):
        s[f"{nome}_4s"] = s[nome].rolling(4).mean()
        s[f"{nome}_8s"] = s[nome].rolling(8).mean()
    semana = s["inicio_semana"].dt.isocalendar().week.astype(float)
    s["semana_sen"], s["semana_cos"] = np.sin(2 * np.pi * semana / 52), np.cos(2 * np.pi * semana / 52)
    s["alvo"] = s["log_casos"].shift(-HORIZONTE)
    s["ano"] = s["inicio_semana"].dt.year
    return s.dropna(subset=CASOS + ["alvo"])


def executar(s, grade=None, avisar=print):
    treino, teste = s[s["ano"].isin(TREINO)], s[s["ano"].isin(TESTE)].dropna(subset=CLIMA)
    treino_clima = treino.dropna(subset=CLIMA)
    erros = {}
    for nome, entradas, base in (("com clima", CASOS + CLIMA, treino_clima), ("sem clima", CASOS, treino_clima)):
        busca = GridSearchCV(XGBRegressor(tree_method="hist", random_state=42, n_jobs=-1), grade or GRADE,
                             scoring="neg_mean_absolute_error", cv=TimeSeriesSplit(4), n_jobs=1)
        busca.fit(base[entradas], base["alvo"])
        previsto = busca.best_estimator_.predict(teste[entradas])
        erros[nome] = float(np.mean(np.abs(previsto - teste["alvo"])))
        if nome == "com clima":
            imp = dict(sorted(zip(entradas, busca.best_estimator_.feature_importances_), key=lambda p: -p[1]))
    aprovado = erros["com clima"] <= (1 - GANHO_MINIMO) * erros["sem clima"]
    avisar(f"semanas: treino {len(treino_clima)} | teste {len(teste)} | previsão {HORIZONTE} semanas à frente")
    avisar(f"Erro médio (log dos casos): com clima {erros['com clima']:.3f} | sem clima {erros['sem clima']:.3f} "
           f"({100 * (1 - erros['com clima'] / erros['sem clima']):+.0f}%)")
    avisar("  (0,10 no log ~ 10% de erro nos casos)")
    avisar("Importância (com clima): " + ", ".join(f"{k} {v:.2f}" for k, v in list(imp.items())[:8]))
    avisar(f"VEREDITO: {'O CLIMA AJUDA' if aprovado else 'O CLIMA NÃO AJUDA'} (precisa de pelo menos {GANHO_MINIMO:.0%} menos erro)")
    return aprovado, erros


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    banco = obter_destino().banco
    dengue = pd.DataFrame(list(banco["silver_arbovirose_semanal"].find(
        {"doenca": "dengue", "ano": {"$gte": 2014, "$lte": 2024}}, {"_id": 0, "inicio_semana": 1, "casos_est": 1})))
    clima = pd.DataFrame(list(banco["silver_clima_era5land_dia"].find(
        {"unidade": {"$regex": "^DS "}, "ano": {"$gte": 2013}}, {"_id": 0, "data": 1, "temp_media_c": 1, "umidade_ar_pct": 1})))
    chuva = pd.DataFrame(list(banco["gold_ml_distrito_dia"].find({}, {"_id": 0, "data": 1, "chuva_dia_mm": 1})))
    linhas = []
    executar(montar(dengue, clima, chuva), avisar=lambda t: (print(t, flush=True), linhas.append(t)))
    (SAIDA / "resultado_dengue_clima.txt").write_text("\n".join(linhas), encoding="utf-8")


if __name__ == "__main__":
    main()
