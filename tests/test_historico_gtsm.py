import zipfile

import numpy as np
import pytest

from etl.historico import gtsm

xr = pytest.importorskip("xarray")
pytest.importorskip("netCDF4")


def _nc(caminho, variavel, valores):
    tempo = np.array(["2022-05-27", "2022-05-28"], dtype="datetime64[ns]")
    ds = xr.Dataset({variavel: (("time", "stations"), np.array(valores, dtype="float32"))},
                    coords={"time": tempo, "stations": [0, 1, 2],
                            "station_x_coordinate": ("stations", [-34.87, -40.0, 10.0]),
                            "station_y_coordinate": ("stations", [-8.05, -3.0, 50.0])})
    ds.to_netcdf(caminho)


def _baixar_falso(pasta):
    def baixar(ano, destino_zip):
        _nc(pasta / "reanalysis_waterlevel_dailymax_2022_05.nc", "waterlevel", [[1.2, 9, 9], [1.6, 9, 9]])
        _nc(pasta / "reanalysis_surge_dailymax_2022_05.nc", "surge", [[0.05, 9, 9], [0.31, 9, 9]])
        with zipfile.ZipFile(destino_zip, "w") as z:
            for nc in pasta.glob("*.nc"):
                z.write(nc, nc.name)
    return baixar


def test_guarda_so_o_ponto_do_recife_e_as_duas_variaveis(destino, tmp_path):
    gtsm.carregar(destino, 2022, 2022, baixar_ano=_baixar_falso(tmp_path), avisar=lambda s: None)
    dias = {d["data"].day: d for d in destino.banco["silver_mare_gtsm_dia"].find()}
    assert (dias[28]["nivel_total_max_m"], dias[28]["ressaca_max_m"]) == (1.6, 0.31)
    assert dias[28]["estacao_gtsm"] == 0                       # o ponto em frente ao Recife, não os outros


def test_retoma_por_ano(destino, tmp_path):
    pedidos = []
    baixar = _baixar_falso(tmp_path)
    gtsm.carregar(destino, 2022, 2022, baixar_ano=lambda a, z: pedidos.append(a) or baixar(a, z), avisar=lambda s: None)
    gtsm.carregar(destino, 2022, 2022, baixar_ano=lambda a, z: pedidos.append(a) or baixar(a, z), avisar=lambda s: None)
    assert pedidos == [2022]


def test_pedido_ao_copernicus():
    p = gtsm.pedido(2019)
    assert p["experiment"] == "reanalysis" and p["temporal_aggregation"] == ["daily_maximum"] and len(p["month"]) == 12
