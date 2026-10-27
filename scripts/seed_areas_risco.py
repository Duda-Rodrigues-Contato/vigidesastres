"""
Carga das areas de risco alto e muito alto (R3/R4) por bairro.

Fontes:
  - areas de risco: Plano de Contingencia 2024 da Defesa Civil do Recife
    (SEDEC), Quadros 04 e 05, transcritos em data/areas_risco_placon2024.csv
  - limites dos bairros: Portal de Dados Abertos do Recife (CKAN)

IMPORTANTE: o plano identifica COMUNIDADES dentro dos bairros, nao bairros
inteiros. A camada diz "este bairro CONTEM areas de risco", e o detalhe
lista quais sao. Pintar o bairro inteiro como risco seria exagerar.

Uso:
    python scripts/seed_areas_risco.py
"""

import csv
import os
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import certifi
import numpy as np
import requests
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import shapely
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

load_dotenv()

RAIZ = Path(__file__).resolve().parent.parent
CSV_RISCO = RAIZ / "data" / "areas_risco_placon2024.csv"
FONTE = "Plano de Contingência 2024 — Defesa Civil do Recife (SEDEC)"

CKAN_API = "https://dados.recife.pe.gov.br/api/3/action/package_show"
DATASET_BAIRROS = "mapas-de-limites-e-divisoes-territoriais"

BANCO = "Recife"
COLECAO = "AreasRisco"
HEADERS = {"User-Agent": "Vigidesastres/0.1 (projeto academico CESAR School)"}

# Nomes do plano que nao sao bairros oficiais (ou abreviados) -> oficiais
APELIDOS = {
    "C. DO BARRETO": ["CAMPINA DO BARRETO"],
    "BREJO BEBERIBE": ["BREJO DE BEBERIBE"],
    "IBURA DE BAIXO": ["IBURA"],  # Ibura de Baixo e parte do bairro Ibura
    "SETUBAL": ["BOA VIAGEM"],  # Setubal e parte do bairro Boa Viagem
    "CORDEIRO / MADALENA": ["CORDEIRO", "MADALENA"],  # area na divisa
}


def normalizar(nome):
    """'Água Fria ' -> 'AGUA FRIA' (sem acento, maiusculo, espacos simples)."""
    sem_acento = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.upper().split())


def ler_planilha():
    with open(CSV_RISCO, encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    print(f"{len(linhas)} areas de risco na planilha ({CSV_RISCO.name})")
    return linhas


def baixar_bairros():
    print(f"Consultando o portal do Recife (dataset: {DATASET_BAIRROS})...")
    r = requests.get(CKAN_API, params={"id": DATASET_BAIRROS}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    recursos = r.json()["result"]["resources"]

    candidatos = [
        x for x in recursos
        if x.get("format", "").upper() == "GEOJSON" and "bairro" in x.get("name", "").lower()
    ]
    if not candidatos:
        nomes = "\n  ".join(f"{x.get('name')} [{x.get('format')}]" for x in recursos)
        sys.exit(f"ERRO: nenhum GeoJSON de bairros no dataset. Recursos:\n  {nomes}")

    recurso = candidatos[0]
    print(f"Recurso: {recurso['name']}")
    arquivo = requests.get(recurso["url"], headers=HEADERS, timeout=120, allow_redirects=True)
    arquivo.raise_for_status()
    return arquivo.json()["features"]


def campo_do_nome(features, nomes_conhecidos):
    """Descobre qual propriedade traz o nome do bairro: a que mais casa
    com os nomes da planilha."""
    placar = {}
    for campo in features[0]["properties"]:
        valores = {normalizar(f["properties"].get(campo) or "") for f in features}
        placar[campo] = len(valores & nomes_conhecidos)

    acertos = max(placar.values(), default=0)
    empatados = [c for c, n in placar.items() if n == acertos and n > 0]

    # O portal costuma ter o nome em duas versoes ("IBURA" e "Ibura").
    # No empate, prefere a grafia normal, com minusculas e acentos,
    # para o mapa nao mostrar tudo em maiusculo.
    def grafia_normal(campo):
        return sum(
            1 for f in features
            if any(ch.islower() for ch in str(f["properties"].get(campo) or ""))
        )

    melhor = max(empatados, key=grafia_normal) if empatados else None
    if not melhor:
        sys.exit(
            "ERRO: nenhuma propriedade parece ser o nome do bairro.\n"
            f"  Propriedades disponiveis: {list(features[0]['properties'])}"
        )
    print(f"Campo do nome do bairro: '{melhor}' ({acertos} nomes reconhecidos)")
    return melhor


def para_latlon(features):
    """Converte de UTM para lat/long se necessario (o Leaflet exige lat/long)."""
    x, y = shape(features[0]["geometry"]).representative_point().coords[0]
    if abs(x) <= 180 and abs(y) <= 90:
        return lambda geom: geom  # ja em lat/long

    try:
        from pyproj import Transformer
    except ImportError:
        sys.exit(
            "ERRO: os bairros vieram em coordenadas projetadas (UTM), nao lat/long.\n"
            "  Instale o conversor e rode de novo:  pip install pyproj"
        )
    # SIRGAS 2000 / UTM 25S, o sistema usado pela prefeitura do Recife
    print(f"Coordenadas em UTM (ex.: {x:.0f}, {y:.0f}) - convertendo para lat/long")
    conversor = Transformer.from_crs("EPSG:31985", "EPSG:4326", always_xy=True)

    def converter(geom):
        def coords(xy):  # xy: matriz N x 2 de coordenadas UTM
            lon, lat = conversor.transform(xy[:, 0], xy[:, 1])
            return np.column_stack([lon, lat])
        return shapely.transform(geom, coords)

    return converter


def cruzar(linhas, features, campo):
    converter = para_latlon(features)
    geometrias = {}
    for f in features:
        nome = normalizar(f["properties"].get(campo) or "")
        geometrias.setdefault(nome, []).append(converter(shape(f["geometry"])))
    nome_oficial = {
        normalizar(f["properties"][campo]): f["properties"][campo] for f in features
    }

    por_bairro, sem_par = {}, set()
    for l in linhas:
        nome_plano = normalizar(l["bairro"])
        destinos = APELIDOS.get(nome_plano, [nome_plano])
        for destino in destinos:
            if destino not in geometrias:
                sem_par.add(l["bairro"])
                continue
            b = por_bairro.setdefault(destino, {"deslizamento": [], "alagamento": []})
            item = l["localidade"]
            if nome_plano != destino:  # deixa claro o nome usado no plano
                item += f" ({l['bairro']})"
            b[l["tipo"]].append(item)

    if sem_par:
        print(f"\n  ATENCAO: {len(sem_par)} bairros do plano sem correspondencia no mapa:")
        for nome in sorted(sem_par):
            print(f"    - {nome}")
        print("  Acrescente o nome oficial em APELIDOS, no topo do script.\n")

    coletado_em = datetime.now(timezone.utc)
    documentos = []
    for nome, riscos in sorted(por_bairro.items()):
        tipos = [t for t in ("alagamento", "deslizamento") if riscos[t]]
        geometria = unary_union(geometrias[nome])
        rotulo = geometria.representative_point()
        documentos.append(
            {
                "bairro": nome_oficial.get(nome, nome),
                "tipos": tipos,
                "alagamento": riscos["alagamento"],
                "deslizamento": riscos["deslizamento"],
                "total_areas": len(riscos["alagamento"]) + len(riscos["deslizamento"]),
                "nivel": "R3/R4 (alto ou muito alto)",
                "geometria": mapping(geometria),
                "ponto_rotulo": [round(rotulo.x, 5), round(rotulo.y, 5)],
                "fonte": FONTE,
                "coletado_em": coletado_em,
            }
        )
    return documentos


def gravar(documentos):
    uri = os.getenv("MONGO_URI")
    if not uri:
        sys.exit("ERRO: MONGO_URI nao encontrada. Confira o .env")
    cliente = MongoClient(uri, server_api=ServerApi("1"), tlsCAFile=certifi.where())
    colecao = cliente[BANCO][COLECAO]
    colecao.drop()  # a planilha e a fonte: recarga completa a cada execucao
    colecao.insert_many(documentos)
    print(f"OK: {colecao.count_documents({})} bairros com areas de risco em {BANCO}.{COLECAO}")


def main():
    linhas = ler_planilha()
    features = baixar_bairros()
    print(f"{len(features)} bairros no mapa do portal")

    conhecidos = {normalizar(l["bairro"]) for l in linhas}
    for destinos in APELIDOS.values():
        conhecidos.update(destinos)
    campo = campo_do_nome(features, conhecidos)

    documentos = cruzar(linhas, features, campo)

    por_tipo = {"alagamento": 0, "deslizamento": 0, "ambos": 0}
    for d in documentos:
        por_tipo["ambos" if len(d["tipos"]) == 2 else d["tipos"][0]] += 1
    print(f"\nBairros: {por_tipo['alagamento']} so alagamento, "
          f"{por_tipo['deslizamento']} so deslizamento, {por_tipo['ambos']} com os dois")

    gravar(documentos)


if __name__ == "__main__":
    main()