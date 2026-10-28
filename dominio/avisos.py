"""Avisos meteorológicos oficiais do INMET: o que vale para o Recife e quão grave é."""

from etl.comum.texto import normalizar

# a escala do INMET, do mais leve ao mais grave
NIVEL_SEVERIDADE = {"PERIGO POTENCIAL": 1, "PERIGO": 2, "GRANDE PERIGO": 3}


def nivel(severidade):
    return NIVEL_SEVERIDADE.get(normalizar(severidade or ""))


def vale_para_recife(areas):
    """O INMET avisa por mesorregião; o Recife fica na Metropolitana (de/do) Recife."""
    return any("METROPOLITANA" in a and "RECIFE" in a for a in (normalizar(x) for x in areas))
