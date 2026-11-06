from datetime import datetime, timedelta, timezone

import pytest

from apps.fontes.repositorios import conexao
from apps.painel.saude import saude_dos_dados

AGORA = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)


@pytest.fixture
def banco(cliente, monkeypatch):
    b = cliente["teste"]
    monkeypatch.setattr(conexao, "banco", lambda: b)
    return b


def _exec(b, fonte, horas_atras, status="ok", erro=None):
    quando = (AGORA - timedelta(hours=horas_atras)).replace(tzinfo=None)
    b["etl_execucoes"].insert_one({"fonte": fonte, "inicio": quando, "fim": quando, "status": status, "erro": erro})


def test_idade_atraso_erro_e_nunca_coletada(banco):
    _exec(banco, "cemaden", 50)          # coleta antiga, ok
    _exec(banco, "cemaden", 2)           # a mais recente vale
    _exec(banco, "previsao", 30)         # passou do prazo de 26 h
    _exec(banco, "mare", 1, "erro", "timeout")
    _exec(banco, "infodengue", 24 * 5)   # semanal: 5 dias está no prazo
    s = {i["rotulo"]: i for i in saude_dos_dados(AGORA)}
    assert (s["Chuva medida"]["texto"], s["Chuva medida"]["estado"]) == ("há 2 h", "ok")
    assert s["Previsão"]["estado"] == "atrasada"
    assert s["Maré"]["estado"] == "erro" and s["Maré"]["detalhe"] == "timeout"
    assert s["InfoDengue"]["estado"] == "ok" and s["InfoDengue"]["texto"] == "há 5 dias"
    assert s["Avisos INMET"]["texto"] == "nunca coletada"
