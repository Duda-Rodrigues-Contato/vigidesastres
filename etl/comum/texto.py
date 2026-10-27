"""Normalização de texto usada para casar nomes entre fontes."""

import unicodedata


def normalizar(nome):
    """'Água Fria ' -> 'AGUA FRIA' (sem acento, maiúsculo, espaços simples)."""
    sem_acento = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.upper().split())
