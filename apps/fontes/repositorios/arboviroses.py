"""Leituras de arboviroses para as telas."""

from . import conexao

GOLD_SEMANA_CIDADE = "gold_arbovirose_semana_cidade"


def resumo_semana_cidade():
    """A semana epidemiológica mais recente, já agregada pelo ETL.

    Devolve None se o ETL ainda não rodou.
    """
    doc = conexao.banco()[GOLD_SEMANA_CIDADE].find_one({}, {"_id": 0}, sort=[("se", -1)])
    if not doc:
        return None
    # semana epidemiológica é DATA, não horário: o valor gravado é meia-noite
    # UTC e converter para o fuso local faria a semana começar no dia anterior
    doc["inicio"] = doc["inicio"].date()
    doc["fim"] = doc["fim"].date()
    return doc


SILVER_BAIRRO_ANO = "silver_arboviroses_bairro_ano"


def anos_por_bairro():
    """Anos com dados por bairro (histórico do SINAN), em ordem."""
    return sorted(conexao.banco()[SILVER_BAIRRO_ANO].distinct("ano"))


def por_bairro(ano, doencas):
    """Casos prováveis por bairro e doença num ano."""
    return list(conexao.banco()[SILVER_BAIRRO_ANO].find(
        {"ano": ano, "doenca": {"$in": list(doencas)}},
        {"_id": 0, "chave": 1, "doenca": 1, "provaveis": 1, "populacao": 1}))
