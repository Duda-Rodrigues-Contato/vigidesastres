"""Maré: identificação das marés cheias na série horária.

O critério de "maré alta" (percentil sobre os picos) está em limiares.py e
na decisão 003. Aqui fica só o que é maré cheia.
"""


def preamares(serie):
    """Picos locais da série (marés cheias), na ordem da série.

    Dado horário: o pico real pode estar até ~30 min antes ou depois da hora
    mostrada. Horas sem nível são ignoradas.
    """
    serie = [r for r in serie if r.get("nivel_m") is not None]
    return [
        atual
        for anterior, atual, seguinte in zip(serie, serie[1:], serie[2:])
        if atual["nivel_m"] > anterior["nivel_m"] and atual["nivel_m"] >= seguinte["nivel_m"]
    ]
