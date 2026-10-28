from datetime import datetime, timedelta, timezone

from dominio.avisos import nivel, vale_para_recife
from etl.fontes import avisos_inmet
from etl.fontes.avisos_inmet import AvisosInmet, ler_feed
from vigidesastre.src.repositorios import avisos as repo_avisos
from vigidesastre.src.repositorios import conexao

AMANHA = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")


def _item(n, severidade, areas, dia_fim):
    tabela = (f"<table><tr><th align='left'>Status</th><td>Alert</td></tr>"
              f"<tr><th align='left'>Evento</th><td>Acumulado de Chuva</td></tr>"
              f"<tr><th align='left'>Severidade</th><td>{severidade}</td></tr>"
              f"<tr><th align='left'>Início</th><td>2026-01-01 00:01:00.0</td></tr>"
              f"<tr><th align='left'>Fim</th><td>{dia_fim} 23:59:00.0</td></tr>"
              f"<tr><th align='left'>Descrição</th><td>Chuva entre 30 a 60 mm/h.</td></tr>"
              f"<tr><th align='left'>Área</th><td>Aviso para as Áreas: {areas}</td></tr>"
              f"<tr><th align='left'>Link Gráfico</th><td><a href='https://avisos.inmet.gov.br/{n}'>https://avisos.inmet.gov.br/{n}</a></td></tr></table>")
    return (f"<item><title>Aviso {n}</title><link>https://apiprevmet3.inmet.gov.br/avisos/rss/{n}</link>"
            f"<description><![CDATA[{tabela}]]></description><guid>https://apiprevmet3.inmet.gov.br/avisos/rss/{n}</guid></item>")


FEED = ("<?xml version='1.0' encoding='UTF-8'?><rss version='2.0'><channel>"
        + _item(1, "Perigo", "Mata Pernambucana, Metropolitana de Recife", AMANHA)
        + _item(2, "Grande Perigo", "Sertão Pernambucano", AMANHA)
        + _item(3, "Perigo Potencial", "Metropolitana do Recife", "2026-01-01")
        + "</channel></rss>")


def test_ler_feed():
    a = ler_feed(FEED)[0]
    assert a["id"] == "1" and a["evento"] == "Acumulado de Chuva" and a["severidade"] == "Perigo"
    assert a["areas"] == ["Mata Pernambucana", "Metropolitana de Recife"]
    assert a["inicio"] == datetime(2026, 1, 1, 3, 1, tzinfo=timezone.utc)   # Brasília -> UTC
    assert a["link"] == "https://avisos.inmet.gov.br/1"


def test_dominio():
    assert nivel("Grande Perigo") == 3 and nivel("perigo potencial") == 1
    assert vale_para_recife(["Metropolitana do Recife"]) and not vale_para_recife(["Sertão Pernambucano"])


def test_so_recife_acumula_e_repositorio(destino, monkeypatch):
    monkeypatch.setattr(avisos_inmet, "get_bytes", lambda url, **k: FEED.encode())
    AvisosInmet(destino).executar()
    AvisosInmet(destino).executar()
    b = destino.banco
    assert sorted(d["id"] for d in b["silver_avisos_inmet"].find()) == ["1", "3"]   # sem o Sertão, sem duplicar
    monkeypatch.setattr(conexao, "banco", lambda: b)
    vigentes = repo_avisos.vigentes_e_proximos()
    assert [v["id"] for v in vigentes] == ["1"] and vigentes[0]["nivel"] == 2        # o 3 já terminou
