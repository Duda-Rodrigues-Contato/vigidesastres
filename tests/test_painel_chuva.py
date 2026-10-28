from datetime import datetime, timedelta, timezone

import pytest

from vigidesastre.src import painel_chuva
from vigidesastre.src.repositorios import conexao

AGORA = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _n(dt):
    return dt.replace(tzinfo=None)  # como o pymongo grava


@pytest.fixture
def banco(cliente, monkeypatch):
    b = cliente["teste"]
    monkeypatch.setattr(conexao, "banco", lambda: b)
    b["silver_chuva_estacoes"].insert_many([
        {"codestacao": "A", "nome": "Alto", "distrito_codigo": 3, "latitude": -8.0, "longitude": -34.9, "ativa": True},
        {"codestacao": "B", "nome": "Baixo", "distrito_codigo": 3, "latitude": -8.1, "longitude": -34.9, "ativa": True},
        {"codestacao": "C", "nome": "Cais", "distrito_codigo": 1, "latitude": -8.05, "longitude": -34.87, "ativa": True},
    ])
    leituras = [("A", 2, 10.0), ("A", 30, 50.0), ("B", 1, 3.0), ("C", 5, 0.0), ("B", 400, 99.0)]  # B 400 h atrás: fora
    b["silver_chuva_leituras"].insert_many([
        {"codestacao": c, "datahora": _n(AGORA - timedelta(hours=h)), "hora": _n(AGORA - timedelta(hours=h)), "chuva_mm": v}
        for c, h, v in leituras])
    b["gold_previsao_distrito"].insert_many([
        {"distrito_codigo": 1, "distrito": "DS I", "chuva_prox_24h_mm": 5.0, "temperatura_c": 29.0, "coletado_em": _n(AGORA)},
        {"distrito_codigo": 3, "distrito": "DS III", "chuva_prox_24h_mm": 40.0, "temperatura_c": 26.0, "coletado_em": _n(AGORA)},
    ])
    b["silver_previsao_horaria"].insert_many([
        {"distrito_codigo": 3, "hora": _n(AGORA + timedelta(hours=h)), "chuva_mm": 2.0} for h in range(1, 4)])
    return b


def test_resumo_usa_pior_estacao_e_pior_previsao(banco):
    r = painel_chuva.resumo_meteo()
    assert r["chuva_24h"] == 10.0 and r["chuva_24h_zona"] == "DS III · Alto"   # o 50 mm foi há 30 h
    assert r["previsao_24h"] == 40.0 and r["previsao_24h_zona"] == "DS III"
    assert (r["temp_min"], r["temp_max"]) == (26.0, 29.0) and r["desatualizado"] is False


def test_gatilhos_por_distrito_com_acumulado_medido(banco):
    d = {x["codigo"]: x for x in painel_chuva.distritos_para_gatilhos()}
    assert d[3]["chuva_72h_mm"] == 60.0 and d[3]["nome"] == "DS III"   # pior estação (A), não a soma com B
    assert d[1]["chuva_72h_mm"] == 0.0


def test_proximas_48h_do_distrito_mais_chuvoso(banco):
    r = painel_chuva.proximas_48h(painel_chuva.distritos_para_gatilhos(), None)
    assert r["zona"] == "DS III" and r["chuva"] == [2.0, 2.0, 2.0]


def test_chuva_diaria_media_e_maximo(banco):
    r = painel_chuva.chuva_diaria()
    assert [s["tipo"] for s in r["series"]] == ["bar", "line"] and len(r["rotulos"]) == 14
    maximos = [v for v in r["series"][1]["valores"] if v is not None]
    assert 50.0 in maximos or 60.0 in maximos                          # o pico de A aparece


def test_geojson_do_mapa(banco):
    poligono = {"type": "Polygon", "coordinates": [[[-34.95, -8.1], [-34.85, -8.1], [-34.85, -8.0], [-34.95, -8.1]]]}
    g = painel_chuva.chuva_por_distrito_geojson([{"properties": {"cdistscodi": 3}, "geometry": poligono},
                                                  {"properties": {"cdistscodi": 5}, "geometry": poligono}])
    p3, p5 = (f["properties"] for f in g["features"])
    assert p3["chuva_24h_mm"] == 10.0 and p3["estacao"] == "Alto" and p3["estacoes"] == 2
    assert p5["chuva_24h_mm"] is None and p5["estacoes"] == 0          # sem estação: sem dado, não zero
    pontos = painel_chuva.estacoes_geojson()["features"]
    assert {p["properties"]["codigo"]: p["properties"]["chuva_24h_mm"] for p in pontos} == {"A": 10.0, "B": 3.0, "C": 0.0}
