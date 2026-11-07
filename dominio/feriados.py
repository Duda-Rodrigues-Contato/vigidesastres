"""Feriados no Recife: nacionais, de Pernambuco e municipais.

A Defesa Civil trabalha em plantão reduzido em feriados e fins de semana: um dia
de chuva forte num feriado pode ter poucos atendimentos REGISTRADOS sem ter tido
poucos problemas. O modelo precisa saber disso.
"""

from datetime import date, timedelta

import holidays


def _pascoa(ano):
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


def feriados_recife(ano):
    """{date: nome} com os feriados nacionais, de PE e do Recife, mais o Carnaval."""
    f = dict(holidays.Brazil(subdiv="PE", years=ano))
    pascoa = _pascoa(ano)
    f[pascoa - timedelta(days=48)] = "Carnaval (segunda)"
    f[pascoa - timedelta(days=47)] = "Carnaval (terça)"
    f[date(ano, 6, 24)] = "São João"
    f[date(ano, 7, 16)] = "Nossa Senhora do Carmo"
    f[date(ano, 12, 8)] = "Nossa Senhora da Conceição"
    return f
