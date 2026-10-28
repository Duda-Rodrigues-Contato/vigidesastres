"""Nomes dos distritos sanitários do Recife (8, desde a reorganização de 2014)."""

ROMANOS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]


def nome_distrito(codigo):
    return f"DS {ROMANOS[codigo - 1]}" if codigo and 1 <= codigo <= len(ROMANOS) else f"DS {codigo}"
