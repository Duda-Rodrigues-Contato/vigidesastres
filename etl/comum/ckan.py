"""Acesso ao Portal de Dados Abertos do Recife (CKAN)."""

from etl import config
from etl.comum.http import get_json


def dataset_por_titulo(busca, trecho_titulo, filtro=None):
    """O primeiro dataset da busca cujo título contém o trecho.

    filtro é o fq do CKAN (ex.: "tags:CREAS"), para datasets que a busca
    por texto não acha.
    """
    params = {"q": busca, "rows": 20}
    if filtro:
        params["fq"] = filtro
    res = get_json(f"{config.CKAN_RECIFE}/package_search", params)
    trecho = trecho_titulo.lower()
    return next((p for p in res["result"]["results"] if trecho in p["title"].lower()), None)

def pacote_por_id(id_dataset):
    """O dataset pelo identificador da URL (ex.: 'distritos-sanitarios')."""
    return get_json(f"{config.CKAN_RECIFE}/package_show", {"id": id_dataset})["result"]


def recurso_por_formato(pacote, formato):
    """O primeiro recurso do formato pedido (GEOJSON, CSV...). Erro se não houver."""
    recurso = next((r for r in pacote["resources"]
                    if (r.get("format") or "").upper() == formato.upper()), None)
    if recurso is None:
        formatos = ", ".join(sorted({r.get("format") or "?" for r in pacote["resources"]}))
        raise ValueError(f"nenhum recurso {formato} em {pacote.get('name')}; há: {formatos}")
    return recurso

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
