"""Maré histórica do Recife, 2014-2024, calculada pela astronomia (etapa 3c do ML).

Não há medição pública e contínua de maré no Recife nesse período: o marégrafo
histórico (PSMSL 556) parou em 1968, e nem o CEMADEN nem o INMET medem nível do
mar ou de rio dentro da cidade (decisão 009). Mas a maré é quase toda
astronômica: segue ciclos da Lua e do Sol que se repetem.

Método (análise harmônica, biblioteca utide):
  1. baixa os últimos 92 dias de nível do mar do Open-Meteo Marine (o máximo da API)
  2. ajusta as componentes de maré (M2, S2, N2, K1, O1...) a essa série
  3. recalcula o nível hora a hora de 2014 a 2024 com essas componentes
  4. resume por dia local: maré máxima, mínima e amplitude

  silver  silver.mare_calculada_dia   uma linha por dia
  silver  silver.mare_calculada_hora  o nível hora a hora (UTC), para saber a maré NA HORA da chuva

Limitação: não inclui ressaca (vento e pressão). Cobre o que mais importa para
alagamento: saber se a chuva caiu em maré de sizígia (as cheias mais altas).
Os níveis são relativos ao nível médio do mar, não ao zero da tábua de marés.

Uso:
    python -m etl.historico.mare
"""

import argparse
from datetime import datetime, timedelta, timezone

import numpy as np

from etl.comum.http import get_json
from etl.destinos import obter_destino
from etl.destinos.base import Carga
from etl.fontes.mare import LATITUDE, LONGITUDE, URL

RECIFE = timezone(timedelta(hours=-3))
TABELA = "silver.mare_calculada_dia"
FONTE = "Maré astronômica calculada (utide) a partir do Open-Meteo Marine"
DIAS_AJUSTE = 92


def serie_recente():
    """(horas UTC como datetime64, níveis) dos últimos DIAS_AJUSTE dias, sem as horas vazias."""
    r = get_json(URL, {"latitude": LATITUDE, "longitude": LONGITUDE, "cell_selection": "sea",
                       "hourly": "sea_level_height_msl", "past_days": DIAS_AJUSTE, "forecast_days": 1,
                       "timeformat": "unixtime", "timezone": "GMT"})
    pares = [(t, v) for t, v in zip(r["hourly"]["time"], r["hourly"]["sea_level_height_msl"]) if v is not None]
    tempos = np.array([np.datetime64(int(t), "s") for t, _ in pares])
    return tempos, np.array([v for _, v in pares], dtype=float)


def ajustar(tempos, niveis):
    """Componentes harmônicas da maré local. Devolve (coef, erro médio do ajuste em metros)."""
    import utide
    coef = utide.solve(tempos, niveis, lat=LATITUDE, method="ols", conf_int="none", verbose=False)
    refeito = utide.reconstruct(tempos, coef, verbose=False).h
    return coef, float(np.sqrt(np.mean((refeito - niveis) ** 2)))


def serie_horaria(coef, inicio, fim):
    """[(hora UTC sem fuso, nível)] de inicio a fim (datas locais do Recife)."""
    import utide
    ini = datetime(inicio.year, inicio.month, inicio.day, tzinfo=RECIFE).astimezone(timezone.utc)
    horas = int(((fim - inicio).days + 1) * 24)
    tempos = np.array([np.datetime64(ini.replace(tzinfo=None) + timedelta(hours=h)) for h in range(horas)])
    nivel = utide.reconstruct(tempos, coef, verbose=False).h
    return [(t.astype(datetime), float(v)) for t, v in zip(tempos, nivel)]


def por_dia(horarios, coletado_em):
    """Série horária resumida por dia local do Recife: máxima, mínima e amplitude."""
    dias = {}
    for t, v in horarios:
        dia = t.replace(tzinfo=timezone.utc).astimezone(RECIFE).date()
        dias.setdefault(dia, []).append(v)
    return [{"data": datetime(d.year, d.month, d.day), "ano": d.year,
             "mare_max_m": round(max(v), 3), "mare_min_m": round(min(v), 3),
             "amplitude_m": round(max(v) - min(v), 3), "fonte": FONTE, "coletado_em": coletado_em}
            for d, v in sorted(dias.items())]


def carregar(destino, inicio, fim, serie=serie_recente, avisar=print):
    tempos, niveis = serie()
    avisar(f"série para o ajuste: {len(niveis)} horas ({len(niveis) / 24:.0f} dias)")
    if len(niveis) < 24 * 30:
        raise ValueError("menos de 30 dias de série: o ajuste das componentes ficaria impreciso")
    coef, erro = ajustar(tempos, niveis)
    principais = sorted(zip(coef.name, coef.A), key=lambda c: -c[1])[:5]
    avisar("componentes principais (amplitude em m): " + ", ".join(f"{n} {a:.2f}" for n, a in principais))
    avisar(f"erro médio do ajuste na série recente: {erro:.2f} m (inclui o que não é maré: vento, pressão)")
    agora = datetime.now(timezone.utc)
    horarios = serie_horaria(coef, inicio, fim)
    linhas = por_dia(horarios, agora)
    destino.carregar(Carga(TABELA, linhas, chaves=("data",)))
    destino.carregar(Carga("silver.mare_calculada_hora",
                           [{"hora": h, "nivel_m": round(v, 3), "fonte": FONTE, "coletado_em": agora}
                            for h, v in horarios], chaves=("hora",)))
    amplitudes = sorted(l["amplitude_m"] for l in linhas)
    avisar(f"{len(linhas)} dias gravados | amplitude diária de {amplitudes[0]:.2f} a {amplitudes[-1]:.2f} m")


def main():
    p = argparse.ArgumentParser(description="Maré histórica calculada (análise harmônica).")
    p.add_argument("--inicio", default="2014-01-01")
    p.add_argument("--fim", default="2024-12-31")
    a = p.parse_args()
    para_data = lambda s: datetime.strptime(s, "%Y-%m-%d").date()
    carregar(obter_destino(), para_data(a.inicio), para_data(a.fim), avisar=lambda s: print(s, flush=True))


if __name__ == "__main__":
    main()
