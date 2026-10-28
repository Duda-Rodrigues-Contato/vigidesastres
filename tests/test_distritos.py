import json

from etl.fontes import distritos
from etl.fontes.distritos import Distritos
from vigidesastre.src.repositorios import conexao, referencia


def _feature(codigo):
    return {"type": "Feature", "properties": {"cdistscodi": codigo},
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}


GEOJSON = {"type": "FeatureCollection", "features": [_feature(c) for c in range(1, 9)]}
PACOTE = {"name": "distritos-sanitarios",
          "resources": [{"format": "CSV", "url": "x"}, {"format": "GeoJSON", "url": "http://x/d.geojson"}]}


def _portal(monkeypatch, geojson=GEOJSON):
    monkeypatch.setattr(distritos, "pacote_por_id", lambda id_: PACOTE)
    monkeypatch.setattr(distritos, "get_bytes", lambda url, **k: json.dumps(geojson).encode())


def test_carga_substitui_e_guarda_bronze(destino, monkeypatch):
    _portal(monkeypatch)
    Distritos(destino).executar()
    Distritos(destino).executar()
    banco = destino.banco
    assert banco["silver_distritos_sanitarios"].count_documents({}) == 8   # não duplica
    assert banco["bronze_distritos"].count_documents({}) == 2             # um por execução


def test_sem_cdistscodi_falha_e_registra(destino, monkeypatch):
    _portal(monkeypatch, {"features": [{"properties": {"outro": 1}, "geometry": {}}]})
    r = Distritos(destino).executar()
    assert r["status"] == "erro" and "cdistscodi" in r["erro"]


def test_repositorio_le_a_silver(destino, monkeypatch):
    _portal(monkeypatch)
    Distritos(destino).executar()
    monkeypatch.setattr(conexao, "banco", lambda: destino.banco)
    assert referencia.total_distritos() == 8
    f = referencia.distritos_features()[0]
    assert "_id" not in f and f["properties"]["cdistscodi"] == 1
