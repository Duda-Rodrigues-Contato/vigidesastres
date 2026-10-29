"""Leituras dos cadastros de referência (distritos, e depois bairros, CNES...)."""

from . import conexao

SILVER_DISTRITOS = "silver_distritos_sanitarios"
SILVER_BAIRROS = "silver_bairros"
SILVER_AREAS_RISCO = "silver_areas_risco"
SILVER_COMUNIDADES = "silver_comunidades"
SILVER_REDE_APOIO = "silver_rede_apoio"
SILVER_UNIDADES = "silver_unidades_saude"


def distritos_features():
    """As Features GeoJSON dos distritos, prontas para o Leaflet."""
    return list(conexao.banco()[SILVER_DISTRITOS].find({}, {"_id": 0}))


def total_distritos():
    return conexao.banco()[SILVER_DISTRITOS].count_documents({})


def areas_risco():
    """Bairros que contêm áreas R3/R4, com as localidades do plano."""
    return list(conexao.banco()[SILVER_AREAS_RISCO].find({}, {"_id": 0}))


def comunidades():
    """Comunidades de Interesse Social, sem o ponto de rótulo (o mapa não usa)."""
    return list(conexao.banco()[SILVER_COMUNIDADES].find({}, {"_id": 0, "ponto_rotulo": 0}))


def rede_apoio(tipo=None):
    """Abrigos, escolas e CRAS; tipo filtra um deles."""
    filtro = {"tipo": tipo} if tipo else {}
    return list(conexao.banco()[SILVER_REDE_APOIO].find(filtro, {"_id": 0}))


def unidades_saude(codigos_tipo=None):
    """Unidades com coordenada (sem ela quebrariam a camada do mapa); filtra por tipo CNES."""
    filtro = {"localizacao": {"$ne": None}}
    if codigos_tipo:
        filtro["codigo_tipo"] = {"$in": list(codigos_tipo)}
    projecao = {"_id": 0, "localizacao": 1, "nome": 1, "tipo": 1, "codigo_tipo": 1, "bairro": 1, "turno": 1}
    return list(conexao.banco()[SILVER_UNIDADES].find(filtro, projecao))


def total_unidades():
    """Mesmo critério do mapa: só unidades com coordenada."""
    return conexao.banco()[SILVER_UNIDADES].count_documents({"localizacao": {"$ne": None}})


def bairros():
    """Bairros com limite e população (IBGE, Censo 2022)."""
    return list(conexao.banco()[SILVER_BAIRROS].find({}, {"_id": 0}))
