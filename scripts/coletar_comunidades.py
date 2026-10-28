"""
Comunidades de Interesse Social (CIS) do Recife, com indicadores de
infraestrutura e risco.

Fonte: Portal de Dados Abertos do Recife, "Relação das favelas, cortiços e
loteamentos irregulares" - 545 polígonos, levantamento de 2014.

O cadastro é de 2014: vale como retrato ESTRUTURAL (drenagem, encosta,
saneamento mudam devagar), não como retrato atual de população.

Os indicadores vêm em notas de 0 a 10 sem dicionário publicado. Antes de
pintar o mapa, este script CONFERE para que lado cada escala cresce,
comparando com o Plano de Contingência 2024 (data/areas_risco_placon2024.csv).

Uso:
    python scripts/coletar_comunidades.py
"""

import csv
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import certifi
import requests
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from shapely.geometry import mapping, shape

from seed_areas_risco import APELIDOS, normalizar

load_dotenv()

API = "https://dados.recife.pe.gov.br/api/3/action"
H = {"User-Agent": "Vigidesastres/0.1 (projeto academico CESAR School)"}
CSV_PLANO = Path(__file__).resolve().parent.parent / "data" / "areas_risco_placon2024.csv"
BANCO = "Recife"
COLECAO = "Comunidades"

# campos guardados (os nomes estão truncados a 10 caracteres na origem)
INDICADORES = {
    "IND_ALAGAM": "alagamento",
    "DENS_ESCOR": "deslizamento",
    "DRENAGEM": "drenagem",
    "ABASTECIME": "abastecimento de água",
    "ESGOTAMENT": "esgotamento sanitário",
    "PAVIMENTAC": "pavimentação",
    "ILUMINACAO": "iluminação",
    "COLETA_LIX": "coleta de lixo",
    "DIST_SAUDE": "distância até saúde",
    "DIST_EDUC": "distância até educação",
    "Indice_COM": "índice composto",
}


def baixar():
    r = requests.get(f"{API}/package_search", params={"q": "favelas", "rows": 10}, headers=H, timeout=60).json()
    pacote = next(p for p in r["result"]["results"] if "favelas" in p["title"].lower())
    recurso = next(x for x in pacote["resources"] if str(x.get("format")).upper() == "GEOJSON")
    print(f"Baixando: {recurso['name']}")
    return requests.get(recurso["url"], headers=H, timeout=180).json()["features"], pacote["title"]


def bairros_do_plano():
    """Bairros que o plano de 2024 aponta para cada tipo de risco."""
    por_tipo = defaultdict(set)
    with open(CSV_PLANO, encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            nome = normalizar(linha["bairro"])
            for destino in APELIDOS.get(nome, [nome]):
                por_tipo[linha["tipo"]].add(destino)
    return por_tipo


def numero(v):
    return v if isinstance(v, (int, float)) else None


def comparar(features, campo, bairros_risco, rotulo):
    """Mediana e % acima de zero, dentro e fora dos bairros do plano."""
    dentro, fora = [], []
    for f in features:
        v = numero(f["properties"].get(campo))
        if v is None:
            continue
        (dentro if normalizar(f["properties"].get("Bairro_Pre") or "") in bairros_risco else fora).append(v)

    def resumo(xs):
        if not xs:
            return "sem dados"
        acima = 100 * sum(1 for x in xs if x > 0) / len(xs)
        return f"n={len(xs):>3} | média {statistics.mean(xs):5.2f} | acima de zero {acima:3.0f}%"

    print(f"\n{rotulo} ({campo})")
    print(f"  nos bairros do plano:  {resumo(dentro)}")
    print(f"  nos demais bairros:    {resumo(fora)}")
    if len(dentro) < 2 or len(fora) < 2:
        print("  -> inconclusivo: poucas comunidades para comparar")
        return
    diferenca = statistics.mean(dentro) - statistics.mean(fora)
    espalhamento = statistics.pstdev(dentro + fora)
    # diferença pequena perto da variação natural é ruído, não confirmação
    if espalhamento == 0 or abs(diferenca) < 0.2 * espalhamento:
        print(f"  -> INCONCLUSIVO: diferença de {diferenca:+.2f} é pequena demais "
              f"perto da variação ({espalhamento:.2f}). Não dá para afirmar a direção.")
    elif diferenca > 0:
        print("  -> nota ALTA = MAIS risco (coerente com o plano)")
    else:
        print("  -> ATENÇÃO: o plano aponta o contrário - a escala pode ser invertida")


def conferir(features):
    plano = bairros_do_plano()
    print("\n== CONFERÊNCIA DAS ESCALAS ==")
    comparar(features, "IND_ALAGAM", plano["alagamento"], "Alagamento")
    comparar(features, "DENS_ESCOR", plano["deslizamento"], "Deslizamento")

    print("\nÍndice composto por classe de precariedade (Indice_COM)")
    por_classe = defaultdict(list)
    for f in features:
        v = numero(f["properties"].get("Indice_COM"))
        if v is not None:
            por_classe[f["properties"].get("Precarieda") or "?"].append(v)
    for classe, xs in sorted(por_classe.items()):
        print(f"  {classe:<40} média {statistics.mean(xs):.2f} (n={len(xs)})")

    print("\nCorrelação com o índice de alagamento (por postos, -1 a +1)")
    base = [numero(f["properties"].get("IND_ALAGAM")) for f in features]
    for campo in ["DRENAGEM", "PAVIMENTAC", "ESGOTAMENT", "Indice_COM"]:
        pares = [(a, numero(f["properties"].get(campo))) for a, f in zip(base, features)]
        pares = [(a, b) for a, b in pares if a is not None and b is not None]
        try:
            r = statistics.correlation(*zip(*pares), method="ranked")
            print(f"  {campo:<11} {r:+.2f}")
        except statistics.StatisticsError:
            print(f"  {campo:<11} sem variação suficiente")


def normalizar_comunidades(features, fonte, coletado_em):
    docs = []
    for f in features:
        p = f["properties"]
        geometria = shape(f["geometry"])
        rotulo = geometria.representative_point()
        docs.append({
            "codigo": p.get("CIS_Geocod"),
            "nome": (p.get("nome_atual") or "").strip() or "(sem nome)",
            "bairro": (p.get("Bairro_Pre") or "").strip(),
            "populacao_2014": numero(p.get("Populacao_")),
            "area_ha": numero(p.get("Area_ha")),
            "precariedade": (p.get("Precarieda") or "").strip(),
            "zeis": numero(p.get("ZEIS")),
            "prioritaria_sanear": (p.get("Prioritari") or "").strip() or None,
            "indicadores": {campo: numero(p.get(campo)) for campo in INDICADORES},
            "geometria": mapping(geometria),
            "ponto_rotulo": [round(rotulo.x, 5), round(rotulo.y, 5)],
            "ano_levantamento": p.get("Ano"),
            "fonte": fonte,
            "coletado_em": coletado_em,
        })
    return docs


def gravar(docs):
    uri = os.getenv("MONGO_URI")
    if not uri:
        sys.exit("ERRO: MONGO_URI não encontrada. Confira o .env")
    colecao = MongoClient(uri, server_api=ServerApi("1"), tlsCAFile=certifi.where())[BANCO][COLECAO]
    colecao.drop()
    colecao.insert_many(docs)
    print(f"\nOK: {colecao.count_documents({})} comunidades em {BANCO}.{COLECAO}")


def main():
    features, fonte = baixar()
    print(f"{len(features)} comunidades")
    conferir(features)
    gravar(normalizar_comunidades(features, fonte, datetime.now(timezone.utc)))


if __name__ == "__main__":
    main()
