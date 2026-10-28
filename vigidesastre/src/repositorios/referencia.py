"""Leituras dos cadastros de referência (distritos, e depois bairros, CNES...)."""

from . import conexao

SILVER_DISTRITOS = "silver_distritos_sanitarios"


def distritos_features():
    """As Features GeoJSON dos distritos, prontas para o Leaflet."""
    return list(conexao.banco()[SILVER_DISTRITOS].find({}, {"_id": 0}))


def total_distritos():
    return conexao.banco()[SILVER_DISTRITOS].count_documents({})
