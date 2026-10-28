import json

from etl.fontes import comunidades
from etl.fontes.comunidades import Comunidades
from vigidesastre.src.repositorios import conexao, referencia


def _cis(codigo, nome, bairro, alagam):
    return {"type": "Feature",
            "properties": {"CIS_Geocod": codigo, "nome_atual": nome, "Bairro_Pre": bairro,
                           "Populacao_": 1200, "IND_ALAGAM": alagam, "DENS_ESCOR": "?", "Ano": 2014},
            "geometry": {"type": "Polygon", "coordinates": [[[-34.9, -8], [-34.89, -8], [-34.89, -8.01], [-34.9, -8]]]}}


FEATURES = [_cis(1, " Vila A ", "Água Fria", 7.5), _cis(2, "", "Ibura", 0)]
PACOTE = {"title": "Relação das favelas", "name": "favelas", "resources": [{"format": "GeoJSON", "url": "http://x"}]}


def _portal(monkeypatch):
    monkeypatch.setattr(comunidades, "dataset_por_titulo", lambda *a: PACOTE)
    monkeypatch.setattr(comunidades, "get_bytes", lambda url, **k: json.dumps({"features": FEATURES}).encode())


def test_normaliza_e_guarda_bronze(destino, monkeypatch):
    _portal(monkeypatch)
    assert Comunidades(destino).executar()["status"] == "ok"
    docs = {d["codigo"]: d for d in destino.banco["silver_comunidades"].find()}
    a, b = docs[1], docs[2]
    assert a["nome"] == "Vila A" and a["chave_bairro"] == "AGUA FRIA"
    assert b["nome"] == "(sem nome)"
    assert a["indicadores"]["IND_ALAGAM"] == 7.5
    assert a["indicadores"]["DENS_ESCOR"] is None          # texto não vira número
    assert a["fonte"] == "Relação das favelas" and len(a["ponto_rotulo"]) == 2
    assert destino.banco["bronze_comunidades"].count_documents({}) == 2


def test_recarga_substitui_e_repositorio(destino, monkeypatch):
    _portal(monkeypatch)
    Comunidades(destino).executar()
    Comunidades(destino).executar()
    monkeypatch.setattr(conexao, "banco", lambda: destino.banco)
    lista = referencia.comunidades()
    assert len(lista) == 2 and "_id" not in lista[0] and "ponto_rotulo" not in lista[0]
