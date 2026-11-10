"""Modelo de EVENTOS (alvo REINDESC): amanhã vai haver deslizamento ou alagamento nesta unidade?

Avaliação melhorada (o que aprendemos nas rodadas com a Defesa Civil):
  - divisão por tempo: ajuste 2016-2022 | limiar em 2023 | TESTE 2024-2026 (anos nunca usados)
  - a PROBABILIDADE é avaliada, não só o alerta: precisão média, Brier e calibração
  - margem de erro por bootstrap (sorteando dias) na diferença para o controle
  - estabilidade: precisão média de cada ano, treinando sempre só com os anos anteriores
  - modelos: regressão logística (simples, base) e XGBoost; controle sem chuva e sem solo
  - régua externa: os gatilhos atuais do sistema (dominio/limiares.py)

Regra de aprovação, fixada ANTES de rodar, no RECIFE (os 8 distritos), no teste 2024-2026:
  1. precisão média do modelo >= a do controle + 0,02, com o limite inferior da margem de erro > 0
  2. F1 do modelo > F1 do melhor gatilho atual
O modelo (logística ou XGBoost) é escolhido pela precisão média na VALIDAÇÃO (2023).

Uso:
    python -m ml.eventos
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, f1_score, precision_score, recall_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from etl.destinos import obter_destino
from ml import linha_base, metricas
from ml.experimento_mare import bootstrap_diferenca
from ml.modelo import META_RECALL, PASTA, ModeloRisco, matriz

SAIDA = Path(__file__).resolve().parents[1] / "analises" / "ml" / "saida"
AJUSTE, VALIDACAO, TESTE = range(2016, 2023), 2023, range(2024, 2027)
CHUVA = ["chuva_dia_mm", "chuva_vespera_mm", "chuva_3d_mm", "chuva_7d_mm", "acumulado_72h_antes", "chuva_memoria",
         "max_hora_mm", "chuva_pico_mm"]
SOLO = ["solo_0_7cm_vespera", "solo_7_28cm_vespera", "solo_28_100cm_vespera"]
MAR = ["mare_hora_pico_m", "mare_max_m"]
CONTEXTO = ["mes", "unidade_codigo"]
ENTRADAS = CHUVA + SOLO + MAR + CONTEXTO
CONTROLE = MAR + CONTEXTO        # o mesmo modelo SEM chuva e SEM solo
MARGEM = 0.02


def carregar(banco):
    df = pd.DataFrame(list(banco["gold_ml_eventos_dia"].find({}, {"_id": 0, "coletado_em": 0})))
    if df.empty:
        raise ValueError("gold_ml_eventos_dia vazia: rode antes python -m etl.derivados.ml_eventos_dia")
    df = df.sort_values(["unidade", "data"]).reset_index(drop=True)
    # maré alta do critério da decisão 003 (para os gatilhos atuais): acima do p80 das 2 semanas anteriores
    limiar = df.groupby("unidade")["mare_max_m"].transform(lambda s: s.shift(1).rolling(14, min_periods=7).quantile(0.8))
    df["mare_alta"] = df["mare_max_m"] >= limiar
    df["critico"] = df["evento"].astype(bool)
    df["dia"] = pd.to_datetime(df["data"]).dt.normalize()
    return df.sort_values("data").reset_index(drop=True)


def escolher_limiar(proba, y, meta=META_RECALL):
    """Mesmo critério do modelo de risco: menos alarmes falsos entre os que avisam >= meta dos eventos."""
    y = np.asarray(y, dtype=bool)
    avaliados = []
    for c in np.unique(np.quantile(proba, np.linspace(0, 0.999, 300))):
        p = proba >= c
        avaliados.append((float(c), recall_score(y, p, zero_division=0), precision_score(y, p, zero_division=0),
                          f1_score(y, p, zero_division=0)))
    na_meta = [a for a in avaliados if a[1] >= meta]
    return max(na_meta, key=lambda a: (a[2], a[0]))[0] if na_meta else max(avaliados, key=lambda a: a[3])[0]


class Logistica:
    """Regressão logística com vazios preenchidos (mediana + indicador) e unidade em colunas 0/1."""
    tipo = "logistica"

    def __init__(self, entradas):
        self.entradas = list(entradas)

    def _x(self, df):
        x = df[self.entradas].astype(float).copy()
        if "unidade_codigo" in x:
            for u in range(1, 15):
                x[f"u{u}"] = (x["unidade_codigo"] == u).astype(float)
            x = x.drop(columns=["unidade_codigo"])
        if "mes" in x:
            x["mes_sen"], x["mes_cos"] = np.sin(2 * np.pi * x["mes"] / 12), np.cos(2 * np.pi * x["mes"] / 12)
            x = x.drop(columns=["mes"])
        return x

    def treinar(self, df, y):
        self.modelo = make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                                    LogisticRegression(class_weight="balanced", max_iter=3000))
        self.modelo.fit(self._x(df), y)
        return self

    def probabilidade(self, df):
        return self.modelo.predict_proba(self._x(df))[:, 1]


class XGB:
    """ModeloRisco (XGBoost) recebendo a tabela inteira; dá para salvar com joblib."""
    tipo = "xgboost"

    def __init__(self, modelo, entradas):
        self.base, self.entradas, self.melhores = modelo, list(entradas), modelo.melhores

    def probabilidade(self, df):
        return self.base.probabilidade(matriz(df, self.entradas))

    def importancia(self):
        return self.base.importancia()


def ajustar(tipo, entradas, ajuste, validacao, treino, grade=None):
    """Hiperparâmetros (XGBoost) no ajuste, limiar na validação, modelo final no treino inteiro."""
    if tipo == "logistica":
        m = Logistica(entradas).treinar(ajuste, ajuste["critico"])
        limiar = escolher_limiar(m.probabilidade(validacao), validacao["critico"])
        ap_val = average_precision_score(validacao["critico"], m.probabilidade(validacao))
        m = Logistica(entradas).treinar(treino, treino["critico"])
    else:
        m = ModeloRisco("xgboost", grade, entradas)
        m.otimizar(matriz(ajuste, entradas), ajuste["critico"])
        m.treinar(matriz(ajuste, entradas), ajuste["critico"])
        proba_val = m.probabilidade(matriz(validacao, entradas))
        limiar, ap_val = escolher_limiar(proba_val, validacao["critico"]), average_precision_score(validacao["critico"], proba_val)
        m.treinar(matriz(treino, entradas), treino["critico"])
        m = XGB(m, entradas)
    m.limiar, m.ap_validacao = limiar, float(ap_val)
    return m


def avaliar(nome, proba, limiar, teste):
    y = teste["critico"].to_numpy()
    previsto = proba >= limiar
    r = metricas.resumo(y, previsto)
    r.update(ap=round(float(average_precision_score(y, proba)), 3), brier=round(float(brier_score_loss(y, proba)), 4),
             grandes=f"{int((previsto & teste['evento_grande'].to_numpy()).sum())}/{int(teste['evento_grande'].sum())}")
    return r


def calibracao(proba, y, faixas=5):
    t = pd.DataFrame({"p": proba, "y": y}).sort_values("p")
    t["faixa"] = pd.qcut(t["p"].rank(method="first"), faixas, labels=False)
    return [(g["p"].mean(), g["y"].mean(), len(g)) for _, g in t.groupby("faixa")]


def executar(df, grade=None, avisar=print, salvar=True):
    ajuste, validacao = df[df["ano"].isin(AJUSTE)], df[df["ano"] == VALIDACAO]
    treino, teste = df[df["ano"] <= VALIDACAO], df[df["ano"].isin(TESTE)]
    recife = teste["recife"].to_numpy(dtype=bool)
    avisar(f"eventos: ajuste {int(ajuste['critico'].sum())} | validação {int(validacao['critico'].sum())} | "
           f"teste {int(teste['critico'].sum())} (Recife {int(teste[recife]['critico'].sum())}) unidade-dias")

    modelos = {"Logística": ajustar("logistica", ENTRADAS, ajuste, validacao, treino),
               "XGBoost": ajustar("xgboost", ENTRADAS, ajuste, validacao, treino, grade),
               "Controle sem chuva e solo": ajustar("xgboost", CONTROLE, ajuste, validacao, treino, grade)}
    for nome, m in modelos.items():
        avisar(f"  {nome}: precisão média na validação {m.ap_validacao:.3f} | limiar {m.limiar:.3f}")
    escolhido = max(("Logística", "XGBoost"), key=lambda n: modelos[n].ap_validacao)
    probas = {n: m.probabilidade(teste) for n, m in modelos.items()}

    resultados = {}
    for recorte, filtro in (("RECIFE", recife), ("Região (14 unidades)", np.ones(len(teste), dtype=bool))):
        t = teste[filtro]
        avisar(f"\nTeste 2024-2026, {recorte} ({int(t['critico'].sum())} unidade-dias com evento):")
        linhas = {"Gatilhos (só ALTO)": linha_base.prever(t, "ALTO").to_numpy(),
                  "Gatilhos (MÉDIO+)": linha_base.prever(t).to_numpy()}
        for n, p in linhas.items():
            r = metricas.resumo(t["critico"], p)
            r["grandes"] = f"{int((p & t['evento_grande'].to_numpy()).sum())}/{int(t['evento_grande'].sum())}"
            resultados[(recorte, n)] = r
            avisar("  " + metricas.texto(n, r) + f" | grandes avisados {r['grandes']}")
        for n, m in modelos.items():
            r = avaliar(n, probas[n][filtro], m.limiar, t)
            resultados[(recorte, n)] = r
            avisar("  " + metricas.texto(n, r) + f" | precisão média {r['ap']:.3f} | Brier {r['brier']:.4f} | "
                   f"grandes avisados {r['grandes']}")

    t = teste[recife]
    (baixo, alto), acima_zero, _ = bootstrap_diferenca(t["critico"].astype(int), probas[escolhido][recife],
                                                       probas["Controle sem chuva e solo"][recife], t["dia"])
    rm, rc = resultados[("RECIFE", escolhido)], resultados[("RECIFE", "Controle sem chuva e solo")]
    melhor_gatilho = max(resultados[("RECIFE", "Gatilhos (só ALTO)")]["f1"], resultados[("RECIFE", "Gatilhos (MÉDIO+)")]["f1"])
    aprovado = rm["ap"] >= rc["ap"] + MARGEM and baixo > 0 and rm["f1"] > melhor_gatilho
    avisar(f"\nEscolhido pela validação: {escolhido}")
    avisar(f"Chuva e solo, no Recife: precisão média {rm['ap']:.3f} x {rc['ap']:.3f} do controle "
           f"(margem de erro {baixo:+.3f} a {alto:+.3f}; ajudou em {acima_zero:.0%} dos sorteios)")
    veredito = (f"precisão média {rm['ap']:.3f} (controle {rc['ap']:.3f}, IC inferior {baixo:+.3f}) | F1 {rm['f1']:.2f} "
                f"(melhor gatilho {melhor_gatilho:.2f}) -> " + ("APROVADO" if aprovado else "NÃO APROVADO"))
    avisar(f"VEREDITO (Recife): {veredito}")

    avisar("\nCalibração no teste (todas as unidades): probabilidade prevista x frequência observada")
    for p, f, n in calibracao(probas[escolhido], teste["critico"].to_numpy()):
        avisar(f"  previsto {p:6.1%} -> aconteceu {f:6.1%} ({n} unidade-dias)")

    avisar("\nEstabilidade (Recife; treino só com os anos anteriores, XGBoost com os mesmos parâmetros):")
    for ano in range(2020, 2027):
        tr, te = df[df["ano"] < ano], df[(df["ano"] == ano) & df["recife"]]
        if te["critico"].sum() == 0 or tr["critico"].sum() == 0:
            continue
        aps = []
        for entradas in (ENTRADAS, CONTROLE):
            m = ModeloRisco("xgboost", None, entradas)
            m.melhores = modelos["XGBoost"].melhores
            m.treinar(matriz(tr, entradas), tr["critico"])
            aps.append(average_precision_score(te["critico"], m.probabilidade(matriz(te, entradas))))
        avisar(f"  {ano}: {int(te['critico'].sum()):>3} eventos | precisão média {aps[0]:.3f} com chuva e solo x "
               f"{aps[1]:.3f} sem")

    imp = getattr(modelos["XGBoost"], "importancia", lambda: {})()
    avisar("\nImportância (XGBoost): " + ", ".join(f"{k} {v:.2f}" for k, v in list(imp.items())[:8]))
    if salvar:
        PASTA.mkdir(exist_ok=True)
        joblib.dump({"tipo": escolhido, "modelo": modelos[escolhido], "limiar": modelos[escolhido].limiar,
                     "entradas": ENTRADAS, "aprovado": aprovado, "veredito": veredito,
                     "treinado_em": datetime.now(timezone.utc).isoformat()}, PASTA / "eventos.joblib")
        avisar(f"Modelo salvo em {PASTA / 'eventos.joblib'}")
    return aprovado, resultados


def main():
    argparse.ArgumentParser(description="Modelo de eventos (REINDESC).").parse_args()
    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas = []

    def avisar(s):
        print(s, flush=True)
        linhas.append(s)
    executar(carregar(obter_destino().banco), avisar=avisar)
    (SAIDA / "resultado_eventos.txt").write_text("\n".join(linhas), encoding="utf-8")


if __name__ == "__main__":
    main()
