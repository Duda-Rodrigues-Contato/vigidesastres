"""Leituras dos avisos oficiais do INMET para as telas."""

from datetime import datetime, timezone

from . import conexao

SILVER_AVISOS = "silver_avisos_inmet"


def vigentes_e_proximos(agora=None):
    """Avisos que ainda não terminaram (em vigor ou a começar), do mais grave ao mais leve."""
    agora = (agora or datetime.now(timezone.utc)).replace(tzinfo=None)  # pymongo grava UTC sem fuso
    return list(
        conexao.banco()[SILVER_AVISOS]
        .find({"fim": {"$gte": agora}}, {"_id": 0})
        .sort([("nivel", -1), ("inicio", 1)])
    )
