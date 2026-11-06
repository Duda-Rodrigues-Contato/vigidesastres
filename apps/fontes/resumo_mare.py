"""Próxima maré cheia e se ela é "alta" pelo critério de limiares.py (decisão 003)."""

import statistics
from datetime import timedelta
from datetime import timezone as dt_timezone

from django.utils import timezone

from dominio import limiares
from dominio.mare import preamares

from .repositorios import mare as repo_mare


def resumo_mare(banco=None):
    """Próxima maré cheia e se ela é "alta" pelo critério de limiares.py.

    "Alta" = entre as marés cheias mais altas dos últimos 14 dias (percentil
    sobre os PICOS, ou seja, as marés de sizígia).
    """
    docs = repo_mare.serie()
    if not docs:
        return None
    for d in docs:
        d["hora"] = d["hora"].replace(tzinfo=dt_timezone.utc)

    agora = timezone.now()
    picos = preamares(docs)
    corte = agora - timedelta(days=14)
    picos_14d = [p["nivel_m"] for p in picos if not p["previsao"] and p["hora"] > corte]
    futuros = [p for p in picos if p["previsao"] and p["hora"] > agora]
    if len(picos_14d) < 5 or not futuros:
        return None  # pouco histórico para o critério relativo, ou sem previsão

    limiar = statistics.quantiles(picos_14d, n=100, method="inclusive")[
        limiares.PERCENTIL_MARE_ALTA - 1
    ]
    janela_24h = [p for p in futuros if p["hora"] <= agora + timedelta(hours=24)] or futuros[:1]
    maior = max(janela_24h, key=lambda p: p["nivel_m"])
    proxima = futuros[0]
    coletado_em = docs[0]["coletado_em"].replace(tzinfo=dt_timezone.utc)

    def quando(p):
        return timezone.localtime(p["hora"]).strftime("%d/%m às %H:%M")

    return {
        "proxima_nivel": proxima["nivel_m"],
        "proxima_quando": quando(proxima),
        "proxima_alta": proxima["nivel_m"] >= limiar,
        "nivel_m": maior["nivel_m"],
        "quando": quando(maior),
        "alta_prevista": maior["nivel_m"] >= limiar,
        "limiar_alta": round(limiar, 2),
        "desatualizado": agora - coletado_em > timedelta(hours=6),
        "_serie": [d for d in docs if d["hora"] > agora],
    }
