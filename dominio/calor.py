"""Calor: índice de calor (sensação térmica) e o gatilho de alerta de calor.

LIMIARES DA LITERATURA, AINDA NÃO CALIBRADOS COM DADOS DE SAÚDE DO RECIFE.

Fonte: NOAA / National Weather Service (EUA), "Heat Index". O índice combina temperatura e
umidade relativa (equação de regressão de Rothfusz, com os ajustes do NWS) e tem quatro faixas:
  27-32 °C  Cautela            fadiga com exposição prolongada
  32-41 °C  Cautela extrema    câimbras e exaustão possíveis; insolação com exposição longa
  41-54 °C  Perigo             câimbras e exaustão prováveis; insolação possível
  >= 54 °C  Perigo extremo     insolação muito provável

Regra do projeto (a calibrar): alerta MÉDIO quando o índice fica na faixa de cautela extrema
por pelo menos HORAS_PERSISTENCIA horas nas próximas 24 h (a persistência pesa mais para a
saúde do que um pico isolado); ALTO quando qualquer hora chega à faixa de perigo.
"""

CAUTELA = 27.0
CAUTELA_EXTREMA = 32.0
PERIGO = 41.0
PERIGO_EXTREMO = 54.0
HORAS_PERSISTENCIA = 3

FAIXAS = [(PERIGO_EXTREMO, "Perigo extremo"), (PERIGO, "Perigo"),
          (CAUTELA_EXTREMA, "Cautela extrema"), (CAUTELA, "Cautela")]


def indice_de_calor(temp_c, umidade_pct):
    """Índice de calor em °C (NWS). Abaixo de ~27 °C o índice é praticamente a temperatura."""
    if temp_c is None or umidade_pct is None:
        return None
    t, rh = temp_c * 9 / 5 + 32, umidade_pct
    simples = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + rh * 0.094)
    if (simples + t) / 2 < 80:
        hi = simples
    else:
        hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh - 0.00683783 * t * t
              - 0.05481717 * rh * rh + 0.00122874 * t * t * rh + 0.00085282 * t * rh * rh
              - 0.00000199 * t * t * rh * rh)
        if rh < 13 and 80 <= t <= 112:
            hi -= ((13 - rh) / 4) * ((17 - abs(t - 95)) / 17) ** 0.5
        elif rh > 85 and 80 <= t <= 87:
            hi += ((rh - 85) / 10) * ((87 - t) / 5)
    return round((hi - 32) * 5 / 9, 1)


def faixa(indice):
    if indice is None:
        return None
    for limite, nome in FAIXAS:
        if indice >= limite:
            return nome
    return "Normal"


def avaliar_calor(distritos):
    """distritos: dicts com nome, indice_calor_max_24h_c e horas_cautela_extrema_24h.
    Devolve alertas SUGERIDOS, no mesmo formato dos gatilhos de chuva."""
    alertas = []
    for d in distritos:
        maximo, horas = d.get("indice_calor_max_24h_c"), d.get("horas_cautela_extrema_24h") or 0
        if maximo is None:
            continue
        nivel = "ALTO" if maximo >= PERIGO else "MÉDIO" if horas >= HORAS_PERSISTENCIA else None
        if nivel:
            texto = f"{maximo:.0f}".replace(".", ",")
            motivo = (f"Sensação térmica de até {texto} °C nas próximas 24 h ({faixa(maximo).lower()}); "
                      f"{horas} h acima de {CAUTELA_EXTREMA:.0f} °C")
            alertas.append({"tipo": "Calor", "nivel": nivel, "zona": d["nome"], "motivo": motivo})
    return alertas
