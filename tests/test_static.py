import pytest
from django.contrib.staticfiles import finders

TELAS = [("/dashboard/", "painel/dashboard.js"), ("/mapa/", "mapa/mapa.js"), ("/alertas/", "alertas/alertas.js"),
         ("/acoes/", "alertas/acoes.js"), ("/relatorios/", "relatorios/relatorios.js")]


@pytest.mark.django_db
@pytest.mark.parametrize("url, js", TELAS)
def test_tela_carrega_seu_js_e_o_arquivo_existe(client, url, js, monkeypatch, cliente):
    from apps.fontes.repositorios import conexao
    monkeypatch.setattr(conexao, "banco", lambda: cliente["teste"])
    monkeypatch.setattr(conexao, "get_mongo_client", lambda: cliente)
    html = client.get(url).content.decode()
    assert f"/static/{js}" in html
    assert finders.find(js), f"{js} não está em nenhuma pasta static/"
