"""Leitura do calendário de risco (gold, calculado por etl/derivados/calendario.py)."""

from . import conexao


def por_mes():
    return list(conexao.banco()["gold_calendario_risco_mes"].find({}, {"_id": 0}).sort([("distrito_codigo", 1), ("mes", 1)]))


def por_distrito():
    return list(conexao.banco()["gold_calendario_risco_distrito"].find({}, {"_id": 0}).sort("distrito_codigo", 1))
