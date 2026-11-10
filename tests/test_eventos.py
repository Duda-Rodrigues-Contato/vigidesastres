import math
import random
from datetime import date, datetime, timedelta

import pandas as pd
from shapely.geometry import box

from dominio.rmr import unidade_da_estacao, unidades
from etl.derivados import ml_eventos_dia as ev
from etl.historico import era5land, reindesc
from ml import eventos

GRADE = {"n_estimators": [60], "max_depth": [3], "learning_rate": [0.1]}
POLIGONOS = {d: box(-35 + d * 0.01, -8.2, -35 + (d + 1) * 0.01, -8.0) for d in range(1, 9)}


def test_unidades_e_estacoes():
    assert len(unidades()) == 14 and unidades()[0] == "DS I"
    assert unidade_da_estacao("261160610A", 3) == "DS III"
    assert unidade_da_estacao("260790601A") == "JABOATÃO DOS GUARARAPES"


def test_reindesc_le_a_pasta_sem_repetir_e_poe_cada_um_na_unidade(tmp_path, destino):
    cab = "Data;UF;Município;Tipologia;Magnitude;Precisão;Latitude;Longitude;Precisão do horário;Horário da ocorrência (UTC);ID ocorrência"
    (tmp_path / "a.csv").write_text(cab + "\n2022-05-28;PE;RECIFE;Geo;GP;MÉDIA;-8.1;-34.965;AUSENTE;;1\n"
                                    "2022-05-28;PE;OLINDA;Hidro;PP;BAIXA;-8.0;-34.86;AUSENTE;;2\n", encoding="utf-8-sig")
    (tmp_path / "b.csv").write_text(cab + "\n2022-05-28;PE;RECIFE;Geo;GP;MÉDIA;-8.1;-34.965;AUSENTE;;1\n"
                                    "2022-05-28;PE;MANAUS;Hidro;PP;BAIXA;-3;-60;AUSENTE;;3\n", encoding="utf-8-sig")
    reindesc.carregar(destino, tmp_path, POLIGONOS, avisar=lambda s: None)
    o = {x["id"]: x for x in destino.banco["silver_reindesc_ocorrencias"].find()}
    assert set(o) == {1, 2} and o[1]["unidade"] == "DS III" and o[2]["unidade"] == "OLINDA"


def test_era5land_resume_por_dia_local(destino):
    def buscar(lat, lon, ini, fim):
        horas = [datetime(2016, 1, 1, 3) + timedelta(hours=h) for h in range(24)]   # 00h a 23h no Recife
        return {"hourly": {"time": [h.isoformat() for h in horas],
                           **{v: [0.3 + i * 0.001 for i in range(24)] for v in era5land.VARIAVEIS}}}
    era5land.carregar(destino, 2016, 2016, buscar=buscar, poligonos=POLIGONOS, avisar=lambda s: None)
    d = destino.banco["silver_clima_era5land_dia"].find_one({"unidade": "DS I", "data": datetime(2016, 1, 1)})
    assert abs(d["solo_0_7cm"] - 0.3115) < 0.001 and d["temp_max_c"] == 0.3


def test_memoria_da_chuva_pesa_mais_a_de_ontem():
    hoje = date(2020, 5, 20)
    serie = {hoje - timedelta(k): 0.0 for k in range(1, 15)}
    serie[hoje - timedelta(1)] = 10.0
    assert ev.memoria(serie, hoje) == 8.5
    serie[hoje - timedelta(1)], serie[hoje - timedelta(10)] = 0.0, 10.0
    assert ev.memoria(serie, hoje) < 2.5


def _tabela():
    """Evento quando a chuva de 3 dias e o solo da véspera são altos (o controle não vê nenhum dos dois)."""
    random.seed(5)
    estacao, solo, eventos_ = {}, {}, {}
    ini, fim = date(2016, 1, 1), date(2026, 6, 30)
    d = ini - timedelta(16)
    while d <= fim:
        base = 8 if d.month in (4, 5, 6) else 2
        for u in ("DS III", "OLINDA"):
            chuva = max(0.0, random.gauss(base, 14))
            cod = "261160603A" if u == "DS III" else "260960601A"
            estacao[(cod, d)] = (chuva, chuva / 3, 24, datetime(d.year, d.month, d.day, 15))
            solo[(u, d)] = {"solo_0_7cm": min(0.5, 0.2 + chuva / 150), "solo_7_28cm": 0.3, "solo_28_100cm": 0.35}
            if chuva > 30 and solo.get((u, d - timedelta(1)), {}).get("solo_0_7cm", 0) > 0.25 and random.random() < 0.7:
                eventos_[(u, d)] = {"n": 1, "geo": 1, "hidro": 0, "gp": int(chuva > 60)}
        d += timedelta(1)
    linhas = ev.montar(estacao, {"261160603A": "DS III", "260960601A": "OLINDA"}, {}, {}, {}, solo, eventos_, ini, fim)
    df = pd.DataFrame([l for l in linhas if l["unidade"] in ("DS III", "OLINDA")])
    return df


def test_modelo_de_eventos_ponta_a_ponta(monkeypatch, tmp_path):
    monkeypatch.setattr(eventos, "PASTA", tmp_path)
    df = _tabela()

    class Banco(dict):
        pass
    banco = {"gold_ml_eventos_dia": type("C", (), {"find": lambda self, *a, **k: df.to_dict("records")})()}
    tabela = eventos.carregar(banco)
    aprovado, resultados = eventos.executar(tabela, grade=GRADE, avisar=lambda s: None)
    xgb, ctrl = resultados[("RECIFE", "XGBoost")], resultados[("RECIFE", "Controle sem chuva e solo")]
    assert xgb["ap"] > ctrl["ap"] + 0.1                         # chuva e solo explicam o alvo simulado
    assert (tmp_path / "eventos.joblib").exists()
