"""Nível real do mar no Recife, com ressaca, 2014-2024: modelo GTSM do Copernicus (chuva x maré).

Fonte: Copernicus Climate Data Store, conjunto "sis-water-level-change-timeseries-cmip6",
experimento "reanalysis": o Global Tide and Surge Model (GTSM, Deltares) alimentado
com vento e pressão reais do ERA5. Separa o que a nossa maré calculada não tem:

  nivel_total_max_m   nível máximo do mar no dia: maré + ressaca + nível médio
  ressaca_max_m       maior "ressaca" do dia (storm surge): o mar acima da maré por vento e pressão

  silver  silver.mare_gtsm_dia   uma linha por dia (dia UTC do arquivo; o máximo diário do Copernicus)

Cada pedido traz o mundo inteiro (43 mil pontos costeiros): baixa um ano por vez,
guarda só o ponto mais próximo do Recife e apaga o resto. Retomável por ano.

Precisa de conta gratuita no CDS (cds.climate.copernicus.eu), aceitar a licença do
conjunto no site e colocar no .env:  CDSAPI_KEY=...  (o token pessoal do perfil).

Uso:
    python -m etl.historico.gtsm                       # 2014 a 2024
    python -m etl.historico.gtsm --inicio 2022 --fim 2022
"""

import argparse
import os
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from etl.destinos import obter_destino
from etl.destinos.base import Carga

CONJUNTO = "sis-water-level-change-timeseries-cmip6"
URL_CDS = "https://cds.climate.copernicus.eu/api"
RECIFE = (-34.87, -8.06)  # lon, lat: em frente ao porto
TABELA = "silver.mare_gtsm_dia"
CONTROLE = "controle_historico"
FONTE = "Copernicus C3S, GTSM v3 (Deltares) forçado com ERA5"
VARIAVEIS = {"total_water_level": ("waterlevel", "nivel_total_max_m"),
             "storm_surge_residual": ("surge", "ressaca_max_m")}


def pedido(ano):
    return {"variable": list(VARIAVEIS), "experiment": "reanalysis", "temporal_aggregation": ["daily_maximum"],
            "year": [str(ano)], "month": [f"{m:02d}" for m in range(1, 13)], "version": ["v3"], "format": "zip"}


def baixar(ano, destino_zip):
    """Pede o ano ao CDS (fica na fila do Copernicus alguns minutos) e salva o zip."""
    import cdsapi
    chave = os.getenv("CDSAPI_KEY")
    if not chave:
        raise RuntimeError("falta CDSAPI_KEY no .env (token do seu perfil no cds.climate.copernicus.eu)")
    cdsapi.Client(url=os.getenv("CDSAPI_URL", URL_CDS), key=chave, quiet=True).retrieve(CONJUNTO, pedido(ano), destino_zip)


def ponto_mais_proximo(ds, alvo=RECIFE):
    import numpy as np
    x, y = ds["station_x_coordinate"].values, ds["station_y_coordinate"].values
    i = int(np.argmin((x - alvo[0]) ** 2 + (y - alvo[1]) ** 2))
    return ds["stations"].values[i], float(x[i]), float(y[i])


def ler_zip(caminho_zip):
    """{data: {coluna: valor}} do ponto mais próximo do Recife, juntando os arquivos mensais das duas variáveis."""
    import xarray as xr
    dias, ponto = {}, None
    with tempfile.TemporaryDirectory() as pasta:
        with zipfile.ZipFile(caminho_zip) as z:
            z.extractall(pasta)
        for nc in sorted(Path(pasta).rglob("*.nc")):
            with xr.open_dataset(nc) as ds:
                variavel = next((v for v, _ in VARIAVEIS.values() if v in ds.data_vars), None)
                if variavel is None:
                    continue
                coluna = next(c for v, c in VARIAVEIS.values() if v == variavel)
                estacao, lon, lat = ponto_mais_proximo(ds)
                ponto = ponto or {"estacao_gtsm": int(estacao), "lon": round(lon, 3), "lat": round(lat, 3)}
                serie = ds[variavel].sel(stations=estacao)
                for t, v in zip(serie["time"].values, serie.values):
                    dia = datetime(1970, 1, 1) + timedelta(seconds=int(t.astype("datetime64[s]").astype(int)))
                    dias.setdefault(dia, {})[coluna] = round(float(v), 3)
    return dias, ponto


def carregar(destino, inicio, fim, baixar_ano=baixar, avisar=print):
    banco = destino.banco
    feitos = {c["mes"] for c in banco[CONTROLE].find({"fonte": "gtsm", "status": "ok"})}
    for ano in range(inicio, fim + 1):
        if str(ano) in feitos:
            avisar(f"  {ano}: já carregado")
            continue
        avisar(f"  {ano}: pedindo ao Copernicus (o pedido entra numa fila; pode levar de 5 a 30 minutos)...")
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = str(Path(pasta) / f"gtsm_{ano}.zip")
            baixar_ano(ano, arquivo)
            dias, ponto = ler_zip(arquivo)
        agora = datetime.now(timezone.utc)
        linhas = [{"data": d, "ano": d.year, **valores, **(ponto or {}), "fonte": FONTE, "coletado_em": agora}
                  for d, valores in sorted(dias.items())]
        if linhas:
            destino.carregar(Carga(TABELA, linhas, chaves=("data",)))
        banco[CONTROLE].update_one({"fonte": "gtsm", "mes": str(ano)},
                                   {"$set": {"status": "ok", "dias": len(linhas), "em": agora}}, upsert=True)
        ressacas = [l["ressaca_max_m"] for l in linhas if "ressaca_max_m" in l]
        avisar(f"  {ano}: {len(linhas)} dias | ponto GTSM {ponto} | maior ressaca do ano "
               f"{max(ressacas) if ressacas else '-'} m")


def main():
    from dotenv import load_dotenv
    load_dotenv()
    p = argparse.ArgumentParser(description="Nível do mar e ressaca do GTSM (Copernicus), por ano, retomável.")
    p.add_argument("--inicio", type=int, default=2014)
    p.add_argument("--fim", type=int, default=2024)
    a = p.parse_args()
    try:
        carregar(obter_destino(), a.inicio, a.fim, avisar=lambda s: print(s, flush=True))
    except KeyboardInterrupt:
        print("\nInterrompido. Rode o mesmo comando para continuar de onde parou.")


if __name__ == "__main__":
    main()
