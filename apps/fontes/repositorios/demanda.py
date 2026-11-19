"""Leitura da previsão de demanda da semana (gold, gravada por python -m ml.demanda --prever)."""

from . import conexao


def previsao():
    return list(conexao.banco()["gold_demanda_previsao"].find({}, {"_id": 0}).sort("distrito_codigo", 1))
