from datetime import datetime

from vigidesastre.src.repositorios import arboviroses, conexao


def test_resumo_vem_da_gold_com_datas_puras(cliente, monkeypatch):
    banco = cliente["Recife"]
    banco["gold_arbovirose_semana_cidade"].insert_many([
        {"se": 202639, "inicio": datetime(2026, 9, 27), "fim": datetime(2026, 10, 3), "estimados": 210},
        {"se": 202640, "inicio": datetime(2026, 10, 4), "fim": datetime(2026, 10, 10), "estimados": 263},
    ])
    monkeypatch.setattr(conexao, "banco", lambda: banco)
    r = arboviroses.resumo_semana_cidade()
    assert r["se"] == 202640 and r["estimados"] == 263        # a mais recente
    assert r["inicio"].isoformat() == "2026-10-04"            # data, sem fuso


def test_resumo_sem_dados_devolve_none(cliente, monkeypatch):
    monkeypatch.setattr(conexao, "banco", lambda: cliente["vazio"])
    assert arboviroses.resumo_semana_cidade() is None
