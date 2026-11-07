from datetime import date, timedelta

import pytest

from apps.fontes.repositorios import conexao
from etl.derivados import calendario as cal

INICIO, FIM = date(2018, 1, 1), date(2019, 12, 31)


def _totais():
    """DS VII: 2 por dia, e 10 por dia de abril a junho. DS VI: 1 por dia, sem estação."""
    t = {}
    d = INICIO
    while d <= FIM:
        t[(7, d)] = 10 if 4 <= d.month <= 6 else 2
        t[(6, d)] = 1
        d += timedelta(1)
    return t


def test_periodo_critico_e_pico():
    meses, distritos = cal.calcular(_totais(), INICIO, FIM)
    r = {d["distrito_codigo"]: d for d in distritos}
    assert r[7]["meses_criticos"] == [4, 5, 6] and r[7]["periodo_critico"] == "abril a junho"
    assert 13 <= r[7]["semana_pico"] <= 27                                 # entre abril e junho
    assert r[6]["periodo_critico"] == "sem período marcadamente acima da média"
    assert r[0]["distrito"] == "Recife"                                      # a cidade inteira também entra
    abril = next(m for m in meses if m["distrito_codigo"] == 7 and m["mes"] == 4)
    assert abril["media_dia"] == 10 and abril["indice"] > 2


def test_periodo_que_atravessa_o_ano():
    indices = [2, 2, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 2]
    assert cal.periodo_critico(indices) == [12, 1, 2]
    assert cal.texto_periodo([12, 1, 2]) == "dezembro a fevereiro"


@pytest.mark.django_db
def test_tela_e_planilha(client, destino, monkeypatch):
    meses, distritos = cal.calcular(_totais(), INICIO, FIM)
    destino.banco["gold_calendario_risco_mes"].insert_many(meses)
    destino.banco["gold_calendario_risco_distrito"].insert_many(distritos)
    monkeypatch.setattr(conexao, "banco", lambda: destino.banco)
    html = client.get("/calendario/").content.decode()
    assert "abril a junho" in html and "DS VII" in html
    linhas = client.get("/calendario/calendario.csv").content.decode("utf-8-sig").splitlines()
    assert len(linhas) == 1 + 12 * 3                                         # Recife, DS VI e DS VII
