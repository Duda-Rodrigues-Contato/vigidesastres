from datetime import datetime, timedelta, timezone

from dominio.mare import preamares
from etl.fontes import mare
from etl.fontes.mare import Mare
from vigidesastre.src.repositorios import conexao
from vigidesastre.src.repositorios import mare as repo_mare

AGORA = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
# 2 h no passado, 4 no futuro; picos em -1 h e +2 h
HORAS = [AGORA + timedelta(hours=h) for h in range(-2, 4)]
NIVEIS = [0.1, 0.9, 0.3, 0.2, 1.1, None]


def _api(monkeypatch, niveis=NIVEIS):
    resposta = {"latitude": -8.0, "longitude": -34.7,
                "hourly": {"time": [int(h.timestamp()) for h in HORAS], "sea_level_height_msl": niveis}}
    monkeypatch.setattr(mare, "get_json", lambda url, params: resposta)


def test_preamares_ignora_nulos():
    serie = [{"nivel_m": n} for n in [0.1, 0.9, None, 0.3, 0.2, 1.1, 1.0]]
    assert [p["nivel_m"] for p in preamares(serie)] == [0.9, 1.1]


def test_upsert_por_hora_e_marca_previsao(destino, monkeypatch):
    _api(monkeypatch)
    Mare(destino).executar()
    Mare(destino).executar()
    banco = destino.banco
    assert banco["silver_mare_horaria"].count_documents({}) == 6       # não duplica
    assert banco["bronze_mare"].count_documents({}) == 2              # uma resposta por coleta
    futuras = banco["silver_mare_horaria"].count_documents({"previsao": True})
    assert futuras == 3


def test_tudo_nulo_falha(destino, monkeypatch):
    _api(monkeypatch, [None] * 6)
    r = Mare(destino).executar()
    assert r["status"] == "erro" and "célula de terra" in r["erro"]


def test_repositorio_ordena_e_tira_nulos(destino, monkeypatch):
    _api(monkeypatch)
    Mare(destino).executar()
    monkeypatch.setattr(conexao, "banco", lambda: destino.banco)
    s = repo_mare.serie()
    assert len(s) == 5 and [x["nivel_m"] for x in s][:2] == [0.1, 0.9]
