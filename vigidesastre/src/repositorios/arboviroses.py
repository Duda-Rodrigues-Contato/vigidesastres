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
