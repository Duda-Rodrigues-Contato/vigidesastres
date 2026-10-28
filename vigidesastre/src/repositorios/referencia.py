"""Leituras dos cadastros de referência (distritos, e depois bairros, CNES...)."""

from . import conexao

SILVER_DISTRITOS = "silver_distritos_sanitarios"
SILVER_AREAS_RISCO = "silver_areas_risco"


def distritos_features():
    """As Features GeoJSON dos distritos, prontas para o Leaflet."""
    return list(conexao.banco()[SILVER_DISTRITOS].find({}, {"_id": 0}))


def total_distritos():
    return conexao.banco()[SILVER_DISTRITOS].count_documents({})


def areas_risco():
    """Bairros que contêm áreas R3/R4, com as localidades do plano."""
    return list(conexao.banco()[SILVER_AREAS_RISCO].find({}, {"_id": 0}))
