"""Carrega os distritos sanitarios do Recife (GeoJSON) no MongoDB."""

import os
import sys

import certifi
import requests
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()

CKAN_API = "https://dados.recife.pe.gov.br/api/3/action/package_show"
DATASET = "distritos-sanitarios"
BANCO = "Recife"
COLECAO = "DistritosSanitarios"


def baixar_geojson():
    print(f"Consultando o portal do Recife (dataset: {DATASET})...")
    resposta = requests.get(CKAN_API, params={"id": DATASET}, timeout=30)
    resposta.raise_for_status()

    recursos = resposta.json()["result"]["resources"]
    geojson = next(
        (r for r in recursos if r.get("format", "").upper() == "GEOJSON"), None
    )

    if geojson is None:
        formatos = ", ".join(sorted({r.get("format", "?") for r in recursos}))
        sys.exit(f"ERRO: nenhum recurso GeoJSON no dataset. Formatos: {formatos}")

    print(f"Recurso encontrado: {geojson['name']}")
    print("Baixando...")

    arquivo = requests.get(geojson["url"], timeout=60, allow_redirects=True)
    arquivo.raise_for_status()
    return arquivo.json()


def inspecionar(features):
    print(f"\n{len(features)} distritos baixados.")

    if not features:
        sys.exit("ERRO: o GeoJSON veio sem features.")

    propriedades = list(features[0].get("properties", {}).keys())
    print(f"Propriedades disponiveis: {propriedades}")

    if "nome_distrito" not in propriedades:
        print(
            "\n  ATENCAO: o campo 'nome_distrito' nao existe neste GeoJSON.\n"
            "  O mapa.html espera esse nome.\n"
            f"  Ajuste o template para um destes: {propriedades}\n"
        )
    else:
        print("OK: campo 'nome_distrito' presente.")


def gravar(features):
    uri = os.getenv("MONGO_URI")
    if not uri:
        sys.exit("ERRO: MONGO_URI nao encontrada. Confira o .env")

    print("\nConectando ao MongoDB...")
    cliente = MongoClient(uri, server_api=ServerApi("1"), tlsCAFile=certifi.where())
    cliente.admin.command("ping")

    colecao = cliente[BANCO][COLECAO]
    colecao.delete_many({})
    colecao.insert_many(features)

    total = colecao.count_documents({})
    print(f"OK: {total} documentos gravados em {BANCO}.{COLECAO}")


def main():
    dados = baixar_geojson()
    features = dados.get("features", [])
    inspecionar(features)
    gravar(features)
    print("\nPronto. Recarregue /mapa/ no navegador.")


if __name__ == "__main__":
    main()
