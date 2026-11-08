"""A maré agrava o alagamento? Teste com e sem maré, no mesmo método do controle sem chuva.

Alvo: houve alagamento registrado pela Defesa Civil no distrito, no dia ou no seguinte
(o registro pode atrasar um dia). Só os distritos de planície (DS I, IV, V, VI), onde a
maré pode represar os canais.

  A. ESCALA DIÁRIA (2015-2024): nível máximo do mar no dia e ressaca (GTSM) e amplitude
     da maré. Treino 2015-2020 | limiar em 2021 | teste 2022-2024.
  B. NA HORA DA CHUVA (2015-2021): o nível da maré NA HORA do pico de chuva do dia
     (chuva horária do INMET + maré calculada hora a hora). É a hipótese física: a chuva
     forte caindo na preamar. Treino 2015-2018 | limiar em 2019 | teste 2020-2021.

Regra fixada ANTES de rodar com os dados reais: a maré tem efeito se o modelo COM maré
superar o modelo SEM maré em pelo menos 0,02 de PRECISÃO MÉDIA (average precision) no teste.
A precisão média mede se a maré traz informação, em qualquer limiar; o F1 depende do limiar
escolhido pela meta de 80% de recall, que nos testes empatava os dois modelos mesmo quando
a maré mudava muito a qualidade da previsão. O F1 é mostrado, mas não decide.

Uso:
    python -m ml.experimento_mare
"""

from pathlib import Path

import pandas as pd
from sklearn.metrics import average_precision_score

from etl.destinos import obter_destino
from ml import dados, metricas
from ml.modelo import ModeloRisco, matriz

SAIDA = Path(__file__).resolve().parents[1] / "analises" / "ml" / "saida"
BASE = ["chuva_dia_mm", "chuva_vespera_mm", "chuva_3d_mm", "chuva_7d_mm", "acumulado_72h_antes", "max_hora_mm",
        "mes", "distrito_codigo"]
MARGEM = 0.02
EXPERIMENTOS = {
    "A": {"titulo": "escala diária (GTSM)", "mar": ["nivel_total_max_m", "ressaca_max_m", "mare_amplitude_m"],
          "treino": range(2015, 2020), "validacao": 2020 + 1, "teste": range(2022, 2025)},
    "B": {"titulo": "maré na hora do pico de chuva (INMET + maré horária)", "mar": ["mare_hora_pico_m", "chuva_pico_mm"],
          "treino": range(2015, 2018), "validacao": 2018 + 1, "teste": range(2020, 2022)},
}


def montar(tabela, gtsm, inmet, mare_hora):
    """Junta tudo por dia e marca o alvo (alagamento em D ou D+1)."""
    df = tabela[tabela["distrito_codigo"].isin(dados.DISTRITOS_PLANICIE)].copy()
    df["dia"] = pd.to_datetime(df["data"]).dt.normalize()
    df = df.sort_values(["distrito_codigo", "dia"])
    seguinte = df.groupby("distrito_codigo")["atendimentos_alagamento"].shift(-1).fillna(0)
    df["critico"] = (df["atendimentos_alagamento"].fillna(0) + seguinte) > 0
    if not gtsm.empty:
        gtsm = gtsm.assign(dia=pd.to_datetime(gtsm["data"]).dt.normalize())
        df = df.merge(gtsm[["dia", "nivel_total_max_m", "ressaca_max_m"]], on="dia", how="left")
    if not inmet.empty and not mare_hora.empty:
        inmet = inmet.dropna(subset=["hora_pico_utc"]).assign(dia=lambda x: pd.to_datetime(x["data"]).dt.normalize())
        nivel = dict(zip(pd.to_datetime(mare_hora["hora"]), mare_hora["nivel_m"]))
        inmet["mare_hora_pico_m"] = pd.to_datetime(inmet["hora_pico_utc"]).dt.floor("h").map(nivel)
        inmet = inmet.rename(columns={"max_hora_mm": "chuva_pico_mm"})
        df = df.merge(inmet[["dia", "mare_hora_pico_m", "chuva_pico_mm"]], on="dia", how="left")
    return df


def rodar(df, cfg, grade=None, avisar=print):
    colunas = BASE + cfg["mar"]
    if not set(cfg["mar"]) <= set(df.columns) or df[cfg["mar"][0]].notna().sum() == 0:
        avisar("   sem os dados deste experimento (veja o passo a passo no docstring)")
        return None
    d = df[df["ano"].isin(list(cfg["treino"]) + [cfg["validacao"]] + list(cfg["teste"]))].dropna(subset=cfg["mar"])
    d = d.sort_values("dia")
    sub, val = d[d["ano"].isin(cfg["treino"])], d[d["ano"] == cfg["validacao"]]
    treino, teste = d[d["ano"] <= cfg["validacao"]], d[d["ano"].isin(cfg["teste"])]
    avisar(f"   treino {len(treino)} linhas ({int(treino['critico'].sum())} com alagamento) | "
           f"teste {len(teste)} ({int(teste['critico'].sum())} com alagamento)")
    resultado = {}
    for nome, entradas in (("com maré", colunas), ("sem maré", BASE)):
        m = ModeloRisco("xgboost", grade, entradas)
        m.otimizar(matriz(treino, entradas), treino["critico"])
        m.escolher_limiar(matriz(sub, entradas), sub["critico"], matriz(val, entradas), val["critico"])
        m.treinar(matriz(treino, entradas), treino["critico"])
        r = metricas.resumo(teste["critico"], m.prever(matriz(teste, entradas)))
        r["ap"] = round(float(average_precision_score(teste["critico"], m.probabilidade(matriz(teste, entradas)))), 3)
        resultado[nome] = (r, m)
        avisar("   " + metricas.texto(nome, r) + f" | precisão média {r['ap']:.3f}")
    com, sem = resultado["com maré"][0], resultado["sem maré"][0]
    efeito = com["ap"] >= sem["ap"] + MARGEM
    imp = resultado["com maré"][1].importancia()
    avisar("   importância (com maré): " + ", ".join(f"{k} {v:.2f}" for k, v in list(imp.items())[:6]))
    avisar(f"   VEREDITO {'A MARÉ TEM EFEITO' if efeito else 'SEM EFEITO DA MARÉ'}: precisão média "
           f"{com['ap']:.3f} com maré x {sem['ap']:.3f} sem ({com['ap'] - sem['ap']:+.3f}) | F1 {com['f1']:.2f} x {sem['f1']:.2f}")
    return efeito


def executar(banco, grade=None, avisar=print):
    tabela = pd.DataFrame(list(banco["gold_ml_distrito_dia"].find({"ano": {"$gte": 2015}}, {"_id": 0, "coletado_em": 0})))
    tabela = dados.preparar(tabela)
    gtsm = pd.DataFrame(list(banco["silver_mare_gtsm_dia"].find({}, {"_id": 0, "data": 1, "nivel_total_max_m": 1,
                                                                      "ressaca_max_m": 1})))
    inmet = pd.DataFrame(list(banco["silver_chuva_inmet_dia"].find({}, {"_id": 0, "data": 1, "max_hora_mm": 1,
                                                                         "hora_pico_utc": 1})))
    mare_hora = pd.DataFrame(list(banco["silver_mare_calculada_hora"].find({}, {"_id": 0, "hora": 1, "nivel_m": 1})))
    if "hora_pico_utc" not in inmet:
        inmet = pd.DataFrame()
    df = montar(tabela, gtsm, inmet, mare_hora)
    vereditos = {}
    for chave, cfg in EXPERIMENTOS.items():
        avisar(f"\nExperimento {chave}: {cfg['titulo']}")
        vereditos[chave] = rodar(df, cfg, grade, avisar)
    return vereditos


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas = []

    def avisar(s):
        print(s, flush=True)
        linhas.append(s)
    executar(obter_destino().banco, avisar=avisar)
    (SAIDA / "experimento_mare.txt").write_text("\n".join(linhas), encoding="utf-8")


if __name__ == "__main__":
    main()
