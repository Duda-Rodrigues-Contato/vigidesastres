from datetime import datetime, timedelta, timezone

from shapely.geometry import box

from etl.fontes import previsao
from etl.fontes.previsao import Previsao

AGORA = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
# 1 h passada, a hora atual e 30 h à frente
HORAS = [AGORA + timedelta(hours=h) for h in range(-1, 31)]


def _serie(chuva_futura):
    return {"latitude": -8.0, "longitude": -34.9, "hourly": {
        "time": [int(h.timestamp()) for h in HORAS],
        "precipitation": [5.0 if h <= AGORA else chuva_futura for h in HORAS],   # passado não conta na previsão
        "temperature_2m": [27.0 if h <= AGORA else 30.0 for h in HORAS]}}


def _api(monkeypatch):
    monkeypatch.setattr(previsao, "distritos_poligonos",
                        lambda: {1: box(-34.95, -8.05, -34.90, -8.00), 2: box(-34.90, -8.05, -34.85, -8.00)})
    monkeypatch.setattr(previsao, "get_json", lambda url, params: [_serie(1.0), _serie(0.5)])


def test_gold_soma_so_o_futuro(destino, monkeypatch):
    _api(monkeypatch)
    assert Previsao(destino).executar()["status"] == "ok"
    g = {d["distrito_codigo"]: d for d in destino.banco["gold_previsao_distrito"].find()}
    # a hora de agora+0 é passado; 24 horas futuras dentro da janela de 24 h
    assert g[1]["chuva_prox_24h_mm"] == 24.0 and g[2]["chuva_prox_24h_mm"] == 12.0
    assert g[1]["chuva_prox_48h_mm"] == 30.0                     # só há 30 h à frente
    assert g[1]["temperatura_c"] == 27.0 and g[1]["distrito"] == "DS I"


def test_upsert_nao_duplica(destino, monkeypatch):
    _api(monkeypatch)
    Previsao(destino).executar()
    Previsao(destino).executar()
    b = destino.banco
    assert b["silver_previsao_horaria"].count_documents({}) == 2 * len(HORAS)
    assert b["gold_previsao_distrito"].count_documents({}) == 2
