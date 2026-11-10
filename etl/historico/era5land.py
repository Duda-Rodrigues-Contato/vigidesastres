"""Umidade do solo e clima do ERA5-Land por unidade do modelo de eventos (2014 até hoje).

Fonte: reanálise ERA5-Land (Copernicus/ECMWF, células de ~9 km), pela API histórica do
Open-Meteo (models=era5_land): aberta, sem cadastro, um ponto por pedido. Um ponto por
unidade: o centro de cada distrito do Recife e de cada município vizinho.

  silver  silver.clima_era5land_dia   unidade x dia local: umidade do solo em 3 camadas,
                                      temperatura (média, máxima, mínima) e umidade do ar

Umidade do solo é a variável física mais direta para deslizamento (solo saturado). Na tabela
do modelo ela entra com UM DIA de atraso (o solo da véspera), que é o que se conhece antes
do dia avaliado. O ERA5-Land chega com ~5 dias de atraso: no uso diário, a umidade do solo
viria da previsão do Open-Meteo, não desta série.

Uso:
    python -m etl.historico.era5land                      # 2014 até 5 dias atrás
    python -m etl.historico.era5land --inicio 2016 --fim 2016
"""

import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from dominio.rmr import VIZINHOS, unidade_do_distrito
from etl.comum.distritos import distritos_poligonos
from etl.comum.http import get_json
from etl.destinos import obter_destino
from etl.destinos.base import Carga

URL = "https://archive-api.open-meteo.com/v1/archive"
VARIAVEIS = ["soil_moisture_0_to_7cm", "soil_moisture_7_to_28cm", "soil_moisture_28_to_100cm",
             "temperature_2m", "relative_humidity_2m"]
RECIFE = timezone(timedelta(hours=-3))
TABELA = "silver.clima_era5land_dia"
CONTROLE = "controle_historico"
FONTE = "ERA5-Land (Copernicus/ECMWF) via Open-Meteo"


def pontos(poligonos=None):
    """{unidade: (lat, lon)}: o centro de cada distrito (ponto interno) e de cada vizinho."""
    poligonos = poligonos or distritos_poligonos()
    res = {}
    for codigo, poli in poligonos.items():
        p = poli.representative_point()
        res[unidade_do_distrito(codigo)] = (round(p.y, 4), round(p.x, 4))
    for nome, _, lon, lat in VIZINHOS.values():
        res[nome] = (lat, lon)
    return res


def por_dia(resposta):
    """Resposta horária (GMT) -> {dia local: {campo: valor}}."""
    h = resposta["hourly"]
    soma, conta, tmax, tmin = defaultdict(float), defaultdict(int), {}, {}
    for i, t in enumerate(h["time"]):
        dia = datetime.fromisoformat(t).replace(tzinfo=timezone.utc).astimezone(RECIFE).date()
        for v in VARIAVEIS:
            x = h[v][i]
            if x is None:
                continue
            soma[(dia, v)] += x
            conta[(dia, v)] += 1
            if v == "temperature_2m":
                tmax[dia], tmin[dia] = max(tmax.get(dia, x), x), min(tmin.get(dia, x), x)
    dias = defaultdict(dict)
    nomes = {"soil_moisture_0_to_7cm": "solo_0_7cm", "soil_moisture_7_to_28cm": "solo_7_28cm",
             "soil_moisture_28_to_100cm": "solo_28_100cm", "temperature_2m": "temp_media_c",
             "relative_humidity_2m": "umidade_ar_pct"}
    for (dia, v), s in soma.items():
        if conta[(dia, v)] >= 20:  # dia quase completo
            dias[dia][nomes[v]] = round(s / conta[(dia, v)], 3)
    for dia in dias:
        dias[dia]["temp_max_c"], dias[dia]["temp_min_c"] = round(tmax[dia], 1), round(tmin[dia], 1)
    return dias


def carregar(destino, inicio, fim, buscar=None, poligonos=None, avisar=print):
    banco = destino.banco
    buscar = buscar or (lambda lat, lon, ini, fim_: get_json(URL, {
        "latitude": lat, "longitude": lon, "start_date": ini, "end_date": fim_, "hourly": ",".join(VARIAVEIS),
        "models": "era5_land", "timezone": "GMT"}))
    feitos = {(c["unidade"], c["mes"]) for c in banco[CONTROLE].find({"fonte": "era5land", "status": "ok"})}
    hoje = date.today()
    for unidade, (lat, lon) in pontos(poligonos).items():
        for ano in range(inicio, fim + 1):
            if (unidade, str(ano)) in feitos:
                continue
            fim_ano = min(date(ano, 12, 31), hoje - timedelta(days=6))
            if fim_ano < date(ano, 1, 1):
                continue
            # 1 dia antes: o 1º de janeiro local começa às 03:00 UTC
            dias = por_dia(buscar(lat, lon, f"{ano - 1}-12-31", fim_ano.isoformat()))
            agora = datetime.now(timezone.utc)
            linhas = [{"unidade": unidade, "data": datetime(d.year, d.month, d.day), "ano": d.year, **v,
                       "latitude": lat, "longitude": lon, "fonte": FONTE, "coletado_em": agora}
                      for d, v in sorted(dias.items()) if d.year == ano]
            if linhas:
                destino.carregar(Carga(TABELA, linhas, chaves=("unidade", "data")))
            completo = fim_ano == date(ano, 12, 31)
            banco[CONTROLE].update_one({"fonte": "era5land", "unidade": unidade, "mes": str(ano)},
                                       {"$set": {"status": "ok" if completo else "parcial", "dias": len(linhas),
                                                 "em": agora}}, upsert=True)
        avisar(f"  {unidade:<26} ({lat}, {lon}) ok")


def main():
    p = argparse.ArgumentParser(description="ERA5-Land por unidade do modelo de eventos (retomável).")
    p.add_argument("--inicio", type=int, default=2014)
    p.add_argument("--fim", type=int, default=date.today().year)
    a = p.parse_args()
    carregar(obter_destino(), a.inicio, a.fim, avisar=lambda s: print(s, flush=True))


if __name__ == "__main__":
    main()
