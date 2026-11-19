from pymongo.errors import ServerSelectionTimeoutError

from apps.mapa import views


def test_api_do_mapa_devolve_503_quando_o_mongo_cai(client, monkeypatch):
    def cai(*a, **k):
        raise ServerSelectionTimeoutError("sem conexão")
    monkeypatch.setattr(views.repo_referencia, "distritos_features", cai)
    r = client.get("/api/distritos/")
    assert r.status_code == 503
    assert "erro" in r.json()
