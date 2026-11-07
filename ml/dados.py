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


def dividir(df):
    return df[df["ano"].isin(ANOS_TREINO)].copy(), df[df["ano"].isin(ANOS_TESTE)].copy()
