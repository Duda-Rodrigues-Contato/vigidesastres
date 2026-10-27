"""
Rede de apoio: abrigos, escolas municipais e CRAS do Recife.

Fonte: Portal de Dados Abertos do Recife
  - "Abrigos - Chuvas no Recife - Acolhimento"   (cadastro, sem capacidade)
  - "Unidades educacionais no município"          (escolas viram abrigo)
  - "Centros de Referência de Assistência Social" (quem opera abrigos)

Todos são endereços de equipamentos públicos, não de pessoas.

O cadastro de abrigos diz ONDE eles ficam, não se estão ABERTOS agora nem
QUANTAS pessoas cabem. Esses dois números ainda dependem da Assistência
Social ou de registro do operador.

Uso:
    python scripts/coletar_rede_apoio.py
"""

import csv
import io
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone

import certifi
import requests
from dotenv import load_dotenv
from ftfy import fix_text
from pymongo import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()

API = "https://dados.recife.pe.gov.br/api/3/action"
H = {"User-Agent": "Vigidesastres/0.1 (projeto academico CESAR School)"}
BANCO = "Recife"
COLECAO = "RedeApoio"

# caixa que envolve o Recife, com folga; ponto fora dela é relatado, não desenhado
LAT_MIN, LAT_MAX = -8.20, -7.90
LON_MIN, LON_MAX = -35.05, -34.80

FONTES = [
    # (tipo, como achar o dataset: busca + trecho do título, ou etiqueta)
    ("abrigo", {"q": "abrigos", "titulo": "abrigos"}),
    ("escola", {"q": "unidades educacionais", "titulo": "unidades educacionais"}),
    ("cras", {"fq": "tags:CREAS", "titulo": "assist"}),
]


def achar_dataset(busca):
    params = {"rows": 20}
    if "q" in busca:
        params["q"] = busca["q"]
    if "fq" in busca:
        params["fq"] = busca["fq"]
    r = requests.get(f"{API}/package_search", params=params, headers=H, timeout=60).json()
    return next(
        (p for p in r["result"]["results"] if busca["titulo"] in p["title"].lower()), None
    )


def ler_tabela(recurso):
    """Lê um recurso tabular, pela API (paginando) ou baixando o CSV."""
    if recurso.get("datastore_active"):
        linhas, offset = [], 0
        while True:
            res = requests.get(
                f"{API}/datastore_search",
                params={"resource_id": recurso["id"], "limit": 1000, "offset": offset},
                headers=H, timeout=120,
            ).json()["result"]
            if not res["records"]:
                break
            linhas += res["records"]
            offset += len(res["records"])
            if offset >= res.get("total", 0):
                break
        return [{k: fix_text(str(v)) if isinstance(v, str) else v for k, v in l.items()} for l in linhas]

    bruto = requests.get(recurso["url"], headers=H, timeout=120).content
    for codificacao in ("utf-8-sig", "latin-1"):
        try:
            texto = fix_text(bruto.decode(codificacao))
            break
        except UnicodeDecodeError:
            continue
    cabecalho = texto.splitlines()[0]
    sep = ";" if cabecalho.count(";") > cabecalho.count(",") else ","
    return list(csv.DictReader(io.StringIO(texto), delimiter=sep))


def campo(linha, *pistas, evitar=()):
    """Primeira coluna cujo nome contém alguma das pistas."""
    for chave in linha:
        nome = chave.lower()
        if any(p in nome for p in pistas) and not any(e in nome for e in evitar):
            return chave
    return None


def numero(valor):
    try:
        return float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def no_recife(lat, lon):
    return LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX


def normalizar(tipo, linhas, fonte, coletado_em):
    if not linhas:
        return [], {}
    exemplo = linhas[0]
    c_nome = campo(exemplo, "nome", "equipamento", "unidade", evitar=("municip",))
    c_bairro = campo(exemplo, "bairro")
    c_end = campo(exemplo, "endereco", "endereço", "logradouro")
    c_num = "N" if "N" in exemplo else campo(exemplo, "numero", "número")
    c_lat = campo(exemplo, "lat")
    c_lon = campo(exemplo, "lon", "lng")
    if not (c_lat and c_lon):
        print(f"  {tipo}: sem colunas de coordenada ({list(exemplo)}), ignorado")
        return [], {}

    extras = [c for c in exemplo if c not in {c_nome, c_bairro, c_end, c_num, c_lat, c_lon, "_id"}]
    docs, conta = [], Counter()
    for l in linhas:
        lat, lon = numero(l.get(c_lat)), numero(l.get(c_lon))
        if lat is None or lon is None:
            conta["sem_coordenada"] += 1
            continue
        if not no_recife(lat, lon) and no_recife(lon, lat):
            lat, lon = lon, lat  # latitude e longitude trocadas na origem
            conta["invertidas"] += 1
        if not no_recife(lat, lon):
            conta["fora_do_recife"] += 1
            continue
        endereco = (l.get(c_end) or "").strip()
        if c_num and str(l.get(c_num) or "").strip():
            endereco += f", {str(l[c_num]).strip()}"
        docs.append({
            "tipo": tipo,
            "nome": (l.get(c_nome) or "").strip() or "(sem nome)",
            "bairro": (l.get(c_bairro) or "").strip(),
            "endereco": endereco,
            "detalhe": {c: l.get(c) for c in extras if str(l.get(c) or "").strip()},
            "localizacao": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "fonte": fonte,
            "coletado_em": coletado_em,
        })
        conta["ok"] += 1
    return docs, conta


def conectar():
    uri = os.getenv("MONGO_URI")
    if not uri:
        sys.exit("ERRO: MONGO_URI não encontrada. Confira o .env")
    return MongoClient(uri, server_api=ServerApi("1"), tlsCAFile=certifi.where())[BANCO]


def main():
    coletado_em = datetime.now(timezone.utc)
    todos = []
    for tipo, busca in FONTES:
        pacote = achar_dataset(busca)
        if not pacote:
            print(f"{tipo}: dataset não encontrado no portal")
            continue
        recursos = [r for r in pacote["resources"] if str(r.get("format")).upper() == "CSV"]
        if not recursos:
            print(f"{tipo}: '{pacote['title']}' não tem arquivo CSV")
            continue
        # o CSV mais recente (os nomes costumam trazer o ano)
        recurso = sorted(recursos, key=lambda r: r.get("name", ""))[-1]
        linhas = ler_tabela(recurso)
        docs, conta = normalizar(tipo, linhas, pacote["title"], coletado_em)
        print(f"{tipo:<7} {recurso.get('name')}: {len(linhas)} linhas -> {dict(conta)}")
        if tipo == "escola":
            situacoes = Counter(d["detalhe"].get("SITUACAO", "?") for d in docs)
            print(f"        situação das escolas: {dict(situacoes)}")
        todos += docs

    if not todos:
        sys.exit("ERRO: nenhum ponto válido.")

    colecao = conectar()[COLECAO]
    colecao.drop()  # o portal é a fonte: recarga completa
    colecao.insert_many(todos)
    colecao.create_index("tipo", name="idx_tipo")
    colecao.create_index([("localizacao", "2dsphere")], name="idx_geo")
    por_tipo = Counter(d["tipo"] for d in todos)
    print(f"\nOK: {len(todos)} pontos em {BANCO}.{COLECAO} -> {dict(por_tipo)}")


if __name__ == "__main__":
    main()