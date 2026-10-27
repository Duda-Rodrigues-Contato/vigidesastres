from datetime import datetime, timezone

import pytest

from etl.fontes import infodengue
from etl.fontes.infodengue import InfoDengue


def _ms(ano, mes, dia):
    """Meia-noite UTC em milissegundos, como a API devolve."""
    return int(datetime(ano, mes, dia, tzinfo=timezone.utc).timestamp() * 1000)


def _reg(se, casos, est, mn, mx, nivel, inicio):
    return {"SE": se, "casos": casos, "casos_est": est, "casos_est_min": mn,
            "casos_est_max": mx, "nivel": nivel, "data_iniSE": inicio, "pop": 1488920}


RESPOSTA = {
    "dengue": [_reg(202640, 25, 253.0, 130, 469, 2, _ms(2026, 10, 4)),
               _reg(202540, 180, 180.0, 180, 180, 2, "2025-09-28")],  # CSV usa texto
    "chikungunya": [_reg(202640, 2, 9.0, 4, 18, 1, _ms(2026, 10, 4)),
                    _reg(202540, 15, 15.0, 15, 15, 1, _ms(2025, 9, 28))],
    "zika": [_reg(202640, 0, 1.0, 0, 3, 1, _ms(2026, 10, 4))],
}


@pytest.fixture
def api_falsa(monkeypatch):
    monkeypatch.setattr(infodengue, "get_json", lambda url, params: RESPOSTA[params["disease"]])


def test_executar_grava_as_tres_camadas(destino, api_falsa):
    registro = InfoDengue(destino, ano=2026).executar()
    assert registro["status"] == "ok"
    banco = destino.banco
    assert banco["bronze_infodengue"].count_documents({}) == 3          # uma por doença
    assert banco["silver_arbovirose_semanal"].count_documents({}) == 5
    assert banco["gold_arbovirose_semana_cidade"].count_documents({}) == 2
    assert banco["etl_execucoes"].count_documents({"status": "ok"}) == 1


def test_gold_soma_as_doencas_e_compara_com_o_ano_anterior(destino, api_falsa):
    InfoDengue(destino, ano=2026).executar()
    g = destino.banco["gold_arbovirose_semana_cidade"].find_one({"se": 202640})
    assert g["estimados"] == 263                       # 253 + 9 + 1
    assert (g["estimados_min"], g["estimados_max"]) == (134, 490)
    assert g["notificados"] == 27
    assert g["nivel"] == 2 and g["nivel_nome"] == "Amarelo" and g["nivel_doenca"] == "dengue"
    assert g["ano_anterior"] == 195                    # 180 + 15
    assert g["inicio"].date().isoformat() == "2026-10-04"
    assert g["fim"].date().isoformat() == "2026-10-10"


def test_rodar_de_novo_atualiza_sem_duplicar(destino, api_falsa):
    InfoDengue(destino, ano=2026).executar()
    InfoDengue(destino, ano=2026).executar()
    assert destino.banco["silver_arbovirose_semanal"].count_documents({}) == 5
    assert destino.banco["gold_arbovirose_semana_cidade"].count_documents({}) == 2


def test_falha_na_fonte_fica_registrada_e_nao_derruba_o_processo(destino, monkeypatch):
    def fora_do_ar(url, params):
        raise ConnectionError("InfoDengue fora do ar")

    monkeypatch.setattr(infodengue, "get_json", fora_do_ar)
    registro = InfoDengue(destino, ano=2026).executar()   # não levanta exceção
    assert registro["status"] == "erro"
    assert "fora do ar" in registro["erro"]
    salvo = destino.banco["etl_execucoes"].find_one()
    assert salvo["status"] == "erro" and salvo["fonte"] == "infodengue"
