from etl.comum import ckan
from etl.comum.texto import normalizar


def test_normalizar_tira_acento_caixa_e_espacos():
    assert normalizar("  Água   Fria ") == "AGUA FRIA"
    assert normalizar("Jardim São Paulo") == normalizar("JARDIM SAO PAULO")


def test_paginacao_avanca_pelo_que_o_servidor_devolve(monkeypatch):
    """Regressão: o portal corta cada resposta em 1.000 linhas mesmo
    quando se pede mais. Avançar por valor fixo pulava registros."""
    linhas = [{"i": i} for i in range(2500)]
    pedidos = []

    def servidor(url, params):
        pedidos.append(params["offset"])
        fim = params["offset"] + min(params["limit"], 1000)
        return {"result": {"records": linhas[params["offset"]:fim], "total": len(linhas)}}

    monkeypatch.setattr(ckan, "get_json", servidor)
    lidas = ckan.ler_datastore("x")
    assert len(lidas) == 2500
    assert [l["i"] for l in lidas] == list(range(2500))
    assert pedidos == [0, 1000, 2000]
