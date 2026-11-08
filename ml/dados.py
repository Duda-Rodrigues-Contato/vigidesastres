"""Carrega a tabela distrito x dia e prepara entradas e alvo (decisão 009)."""

import pandas as pd

ANOS_TREINO = range(2015, 2022)
ANOS_TESTE = range(2022, 2025)
PERCENTIL_CRITICO = 0.95
MINIMO_CRITICO = 5
DISTRITOS_PLANICIE = (1, 4, 5, 6)   # onde a maré pode represar a drenagem
DISTRITOS_MORRO = (2, 3, 7, 8)


def carregar(banco):
    """DataFrame da gold.ml_distrito_dia, sem 2014 (alvo incompleto naquele ano)."""
    df = pd.DataFrame(list(banco["gold_ml_distrito_dia"].find({"ano": {"$gte": 2015}}, {"_id": 0, "coletado_em": 0})))
    if df.empty:
        raise ValueError("gold_ml_distrito_dia vazia: rode antes python -m etl.derivados.ml_distrito_dia")
    return preparar(df)


def preparar(df):
    """Entradas derivadas, sempre com informação disponível ANTES do dia avaliado.

    acumulado_72h_antes: chuva dos 3 dias anteriores (no uso diário, é a medida até hoje)
    mare_alta: maré do dia acima do percentil 80 das últimas 2 semanas (critério da decisão 003)
    """
    df = df.sort_values(["distrito_codigo", "data"]).reset_index(drop=True)
    por_distrito = df.groupby("distrito_codigo", group_keys=False)
    df["acumulado_72h_antes"] = por_distrito["chuva_3d_mm"].shift(1)
    limiar_mare = df.groupby("distrito_codigo")["mare_max_m"].transform(
        lambda s: s.shift(1).rolling(14, min_periods=7).quantile(0.80))
    df["mare_alta"] = df["mare_max_m"] >= limiar_mare
    df["planicie"] = df["distrito_codigo"].isin(DISTRITOS_PLANICIE)
    if "atendimentos_alagamento" in df and "atendimentos_deslizamento" in df:
        # eventos físicos: o que a chuva causa diretamente (sem lonas, que seguem campanhas)
        df["atendimentos_fisicos"] = df["atendimentos_alagamento"].fillna(0) + df["atendimentos_deslizamento"].fillna(0)
    return df


def cortes_do_treino(df):
    """Corte de dia crítico por distrito: p95 dos atendimentos ligados à chuva NO TREINO, mínimo 5."""
    treino = df[df["ano"].isin(ANOS_TREINO)]
    return {d: max(MINIMO_CRITICO, float(s.quantile(PERCENTIL_CRITICO)))
            for d, s in treino.groupby("distrito_codigo")["atendimentos_chuva"]}


def marcar_critico(df, cortes):
    df = df.copy()
    df["critico"] = df["atendimentos_chuva"] >= df["distrito_codigo"].map(cortes)
    return df


FATOR_PICO = 3            # pico = 3 vezes a rotina recente
JANELA_BASE = 28          # rotina: média diária dos 28 dias ANTERIORES
JANELA_RESPOSTA = 3       # resposta: o MAIOR dia entre D, D+1 e D+2 (absorve o atraso do fim de semana)
MINIMO_PICO = 5           # nunca é pico com menos de 5 atendimentos no dia
EXCESSO_MINIMO = 10       # e precisa passar a rotina em pelo menos 10 atendimentos: numa rotina de
                          # 1 por dia, 5 atendimentos são variação comum, não um evento


# alvos testados (decisão 009): todos os atendimentos ligados à chuva, ou só os eventos físicos
ALVOS = {
    "chuva": {"coluna": "atendimentos_chuva", "excesso": EXCESSO_MINIMO, "minimo": MINIMO_PICO},
    # alagamento e deslizamento são mais raros: excesso e mínimo de 3 (fixados ANTES de rodar)
    "fisico": {"coluna": "atendimentos_fisicos", "excesso": 3, "minimo": 3},
}


def marcar_pico(df, alvo="chuva"):
    """Alvo da decisão 009 (revisada): o distrito teve um PICO de atendimentos ligados à chuva,
    acima da sua própria rotina recente?

    Comparar com a rotina dos 28 dias anteriores tira o que é trabalho programado (campanha de
    lonas na estação chuvosa eleva a rotina e não vira pico) e a tendência de queda dos registros
    ao longo dos anos. Usa só o passado para a rotina; o futuro (D+1, D+2) entra só no alvo.
    """
    cfg = ALVOS[alvo]
    df = df.sort_values(["distrito_codigo", "data"]).copy()
    g = df.groupby("distrito_codigo")[cfg["coluna"]]
    rotina = g.transform(lambda s: s.shift(1).rolling(JANELA_BASE, min_periods=14).mean())
    resposta = g.transform(lambda s: s[::-1].rolling(JANELA_RESPOSTA, min_periods=JANELA_RESPOSTA).max()[::-1])
    df["rotina_28d"] = rotina
    df["resposta_3d"] = resposta
    limite = pd.concat([FATOR_PICO * rotina, rotina + cfg["excesso"]], axis=1).max(axis=1).clip(lower=cfg["minimo"])
    df["critico"] = (resposta >= limite) & rotina.notna() & resposta.notna()
    return df


def dividir(df):
    return df[df["ano"].isin(ANOS_TREINO)].copy(), df[df["ano"].isin(ANOS_TESTE)].copy()
