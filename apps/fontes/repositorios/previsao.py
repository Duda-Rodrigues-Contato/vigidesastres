"""Leituras da previsão (Open-Meteo, modelo) para as telas."""

from datetime import timezone

from . import conexao

GOLD = "gold_previsao_distrito"
SILVER = "silver_previsao_horaria"


def por_distrito():
    """Um documento por distrito: chuva prevista 24 h e 48 h, temperatura, coletado_em."""
    return list(conexao.banco()[GOLD].find({}, {"_id": 0}).sort("distrito_codigo", 1))


def serie_futura(distrito_codigo, inicio, fim):
    """Previsão hora a hora de um distrito entre `inicio` e `fim` (datas com fuso)."""
    def naive(dt):
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return list(conexao.banco()[SILVER].find(
        {"distrito_codigo": distrito_codigo, "hora": {"$gt": naive(inicio), "$lte": naive(fim)}},
        {"_id": 0, "hora": 1, "chuva_mm": 1}).sort("hora", 1))
