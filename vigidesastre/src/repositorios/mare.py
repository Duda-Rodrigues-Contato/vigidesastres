"""Leituras de maré para as telas."""

from . import conexao

SILVER_MARE = "silver_mare_horaria"


def serie():
    """A série horária com nível, em ordem de hora (passado e previsão)."""
    return list(
        conexao.banco()[SILVER_MARE]
        .find({"nivel_m": {"$ne": None}}, {"_id": 0, "hora": 1, "nivel_m": 1, "previsao": 1, "coletado_em": 1})
        .sort("hora", 1)
    )
