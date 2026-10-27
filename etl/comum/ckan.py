"""Acesso ao Portal de Dados Abertos do Recife (CKAN)."""

from etl import config
from etl.comum.http import get_json


def dataset_por_titulo(busca, trecho_titulo):
    res = get_json(f"{config.CKAN_RECIFE}/package_search", {"q": busca, "rows": 20})
    trecho = trecho_titulo.lower()
    return next((p for p in res["result"]["results"] if trecho in p["title"].lower()), None)


def ler_datastore(resource_id, campos=None):
    """Lê todas as linhas de um recurso.

    Avança pelo número de linhas que o servidor DEVOLVEU, não pelo que foi
    pedido: o portal corta cada resposta em 1.000 linhas mesmo quando se
    pede mais, e avançar por um valor fixo pularia registros sem avisar.
    """
    params = {"resource_id": resource_id, "limit": 1000, "offset": 0}
    if campos:
        params["fields"] = ",".join(campos)
    linhas = []
    while True:
        res = get_json(f"{config.CKAN_RECIFE}/datastore_search", params)["result"]
        lote = res["records"]
        if not lote:
            break
        linhas += lote
        params["offset"] += len(lote)
        if params["offset"] >= res.get("total", 0):
            break
    return linhas
