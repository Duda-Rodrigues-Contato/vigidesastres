"""
Arboviroses por bairro do Recife: casos prováveis e incidência anual.

Fontes:
  - casos: SINAN, publicado pela Secretaria de Saúde no Portal de Dados
    Abertos do Recife (dataset "Casos de Dengue, Zika e Chikungunya"),
    um arquivo por doença e ano. Dados por BAIRRO DE RESIDÊNCIA.
  - população: IBGE, Censo 2022, agregados por bairro
  - limites dos bairros: Portal de Dados Abertos do Recife

Critério: casos PROVÁVEIS = notificados exceto descartados, o mesmo dos
boletins da prefeitura. Incidência por 10 mil habitantes.

LGPD: o arquivo público traz data de nascimento, rua, CEP, raça/cor e
comorbidades de cada pessoa. Este conector pede à API SÓ os campos de que
precisa, e grava SÓ totais por bairro e ano. Exceção consciente ao padrão
"raw antes de normalizar": com dado pessoal de saúde vale a minimização.

Uso:
    python scripts/coletar_arboviroses_bairros.py               # 2016 a 2025
    python scripts/coletar_arboviroses_bairros.py 2024 2025     # só esses anos
"""

import csv
import io
import os
import re
import sys
import time
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone

import certifi
import requests
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

# funções já testadas na carga das áreas de risco
from seed_areas_risco import baixar_bairros, campo_do_nome, normalizar, para_latlon

load_dotenv()

CKAN = "https://dados.recife.pe.gov.br/api/3/action"
TITULO_DATASET = "Casos de Dengue, Zika e Chikungunya"
IBGE_BAIRROS = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/"
    "Agregados_por_Bairro_csv/Agregados_por_bairros_basico_BR_20260520.zip"
)
COD_RECIFE_IBGE = "2611606"
COD_RECIFE_SINAN = 261160
POPULACAO_RECIFE_2022 = 1_488_920  # usada para conferir a coluna do IBGE

ANO_INICIAL = 2016  # o formato dos arquivos mudou em 2016
CAMPOS = ["CLASSI_FIN", "NM_BAIRRO", "ID_MN_RESI"]  # só o necessário (LGPD)
DESCARTADO = 5  # CLASSI_FIN no SINAN

BANCO = "Recife"
HEADERS = {"User-Agent": "Vigidesastres/0.1 (projeto academico CESAR School)"}

# nomes do SINAN que não batem com os do IBGE depois de normalizar
APELIDOS_SINAN = {
    "BAIRRO DO RECIFE": "RECIFE",
    "RECIFE ANTIGO": "RECIFE",
}


# ─── população (IBGE) ────────────────────────────────────────────────────

def populacao_por_bairro():
    print("Baixando população por bairro (IBGE, Censo 2022)...")
    conteudo = requests.get(IBGE_BAIRROS, headers=HEADERS, timeout=180).content
    zip_ = zipfile.ZipFile(io.BytesIO(conteudo))
    nome = next(n for n in zip_.namelist() if n.lower().endswith(".csv"))
    texto = zip_.read(nome).decode("latin-1")
    linhas = csv.DictReader(io.StringIO(texto), delimiter=";")

    bairros = {}
    for l in linhas:
        if l["CD_MUN"] != COD_RECIFE_IBGE:
            continue
        bairros[normalizar(l["NM_BAIRRO"])] = {
            "nome": l["NM_BAIRRO"],
            "cd_bairro_ibge": l["CD_BAIRRO"],
            "populacao": int(l["v0001"]),
            "area_km2": float(l["AREA_KM2"].replace(",", ".")),
        }

    total = sum(b["populacao"] for b in bairros.values())
    print(f"  {len(bairros)} bairros, população somada: {total:,}".replace(",", "."))
    if abs(total - POPULACAO_RECIFE_2022) > POPULACAO_RECIFE_2022 * 0.01:
        sys.exit(
            f"ERRO: a soma ({total}) não bate com a população do Recife "
            f"({POPULACAO_RECIFE_2022}). A coluna v0001 pode não ser o total de pessoas."
        )
    print("  OK: a soma confere com a população do Recife no Censo 2022")
    return bairros


# ─── casos (SINAN via portal) ────────────────────────────────────────────

def recursos_de_casos(anos):
    """Acha os arquivos por doença e ano no dataset da prefeitura."""
    r = requests.get(f"{CKAN}/package_search", params={"q": "dengue", "rows": 20},
                     headers=HEADERS, timeout=60).json()
    pacote = next(
        (p for p in r["result"]["results"] if p["title"].strip() == TITULO_DATASET), None
    )
    if not pacote:
        sys.exit(f"ERRO: dataset '{TITULO_DATASET}' não encontrado no portal.")

    arquivos = []
    for rec in pacote["resources"]:
        nome = rec.get("name", "")
        ano = re.search(r"(20\d\d)", nome)
        doenca = next((d for d in ("dengue", "chikungunya", "zika") if d in nome.lower()), None)
        if not (ano and doenca) or "metadado" in nome.lower():
            continue
        if int(ano.group(1)) in anos:
            arquivos.append({"doenca": doenca, "ano": int(ano.group(1)), "id": rec["id"]})
    return sorted(arquivos, key=lambda a: (a["ano"], a["doenca"]))


def buscar(params, tentativas=3):
    for t in range(1, tentativas + 1):
        try:
            r = requests.get(f"{CKAN}/datastore_search", params=params, headers=HEADERS, timeout=120)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as erro:
            if t == tentativas:
                raise
            time.sleep(2**t)


def ler_casos(arquivo):
    """Lê só os campos necessários, avançando pelo que o servidor devolve
    (ele limita cada resposta a 1.000 linhas, mesmo pedindo mais)."""
    disponiveis = {f["id"] for f in buscar({"resource_id": arquivo["id"], "limit": 0})["result"]["fields"]}
    campos = [c for c in CAMPOS if c in disponiveis]
    if "NM_BAIRRO" not in campos:
        print(f"  {arquivo['doenca']} {arquivo['ano']}: sem coluna de bairro, ignorado")
        return []

    linhas, offset = [], 0
    while True:
        res = buscar({"resource_id": arquivo["id"], "fields": ",".join(campos),
                      "limit": 1000, "offset": offset})["result"]
        lote = res["records"]
        if not lote:
            break
        linhas += lote
        offset += len(lote)
        if offset >= res.get("total", 0):
            break
    return linhas


def agregar(linhas, arquivo, bairros_ibge):
    """Totais por bairro. Nada individual sai desta função."""
    contagem = defaultdict(lambda: {"notificados": 0, "descartados": 0})
    classes = Counter()
    sem_bairro = fora_do_recife = 0
    nao_reconhecidos = Counter()

    for l in linhas:
        if "ID_MN_RESI" in l and l["ID_MN_RESI"] not in (None, "", COD_RECIFE_SINAN):
            fora_do_recife += 1
            continue
        classes[l.get("CLASSI_FIN")] += 1
        nome = normalizar(l.get("NM_BAIRRO") or "")
        nome = APELIDOS_SINAN.get(nome, nome)
        if not nome:
            sem_bairro += 1
            continue
        if nome not in bairros_ibge:
            nao_reconhecidos[nome] += 1
            continue
        contagem[nome]["notificados"] += 1
        if l.get("CLASSI_FIN") == DESCARTADO:
            contagem[nome]["descartados"] += 1

    perdidos = sum(nao_reconhecidos.values())
    print(
        f"  {arquivo['doenca']:<12} {arquivo['ano']}: {len(linhas):>6} linhas | "
        f"sem bairro {sem_bairro} | nome não reconhecido {perdidos} | fora do Recife {fora_do_recife}"
    )
    print("      classificação final:", dict(classes.most_common()))
    if nao_reconhecidos:
        print("      nomes não reconhecidos:", ", ".join(f"{n} ({q})" for n, q in nao_reconhecidos.most_common(6)))
    return contagem, {
        "doenca": arquivo["doenca"], "ano": arquivo["ano"], "linhas": len(linhas),
        "sem_bairro": sem_bairro, "nao_reconhecidos": perdidos, "fora_do_recife": fora_do_recife,
        "classificacao": {str(k): v for k, v in classes.items()},
    }


# ─── gravação ────────────────────────────────────────────────────────────

def conectar():
    uri = os.getenv("MONGO_URI")
    if not uri:
        sys.exit("ERRO: MONGO_URI não encontrada. Confira o .env")
    return MongoClient(uri, server_api=ServerApi("1"), tlsCAFile=certifi.where())[BANCO]


def gravar_bairros(banco, bairros_ibge):
    """Limites + população num lugar só, para servir a várias camadas."""
    features = baixar_bairros()
    campo = campo_do_nome(features, set(bairros_ibge))
    converter = para_latlon(features)

    geometrias = defaultdict(list)
    for f in features:
        geometrias[normalizar(f["properties"].get(campo) or "")].append(converter(shape(f["geometry"])))

    docs = []
    for chave, b in bairros_ibge.items():
        if chave not in geometrias:
            print(f"  bairro do IBGE sem limite no mapa: {b['nome']}")
            continue
        docs.append({**b, "chave": chave, "geometria": mapping(unary_union(geometrias[chave]))})

    banco["Bairros"].drop()
    banco["Bairros"].insert_many(docs)
    print(f"OK: {len(docs)} bairros com limite e população em {BANCO}.Bairros")


def main():
    anos = [int(a) for a in sys.argv[1:]] or list(range(ANO_INICIAL, datetime.now().year))
    coletado_em = datetime.now(timezone.utc)
    banco = conectar()

    bairros_ibge = populacao_por_bairro()
    gravar_bairros(banco, bairros_ibge)

    arquivos = recursos_de_casos(anos)
    print(f"\n{len(arquivos)} arquivos de casos para {min(anos)}-{max(anos)}:")

    colecao = banco["ArboviroseBairroAnual"]
    colecao.create_index([("doenca", 1), ("ano", 1), ("chave", 1)], unique=True, name="idx_doenca_ano_bairro")

    for arquivo in arquivos:
        contagem, qualidade = agregar(ler_casos(arquivo), arquivo, bairros_ibge)

        # recarga completa do par doença+ano: o arquivo da prefeitura é a verdade
        colecao.delete_many({"doenca": arquivo["doenca"], "ano": arquivo["ano"]})
        docs = []
        for chave, b in bairros_ibge.items():
            c = contagem.get(chave, {"notificados": 0, "descartados": 0})
            provaveis = c["notificados"] - c["descartados"]
            docs.append({
                "doenca": arquivo["doenca"], "ano": arquivo["ano"],
                "chave": chave, "bairro": b["nome"],
                "notificados": c["notificados"], "descartados": c["descartados"],
                "provaveis": provaveis, "populacao": b["populacao"],
                "incidencia_10k": round(provaveis / b["populacao"] * 10_000, 1) if b["populacao"] else None,
                "coletado_em": coletado_em,
            })
        colecao.insert_many(docs)
        banco["QualidadeArboviroses"].replace_one(
            {"doenca": arquivo["doenca"], "ano": arquivo["ano"]},
            {**qualidade, "coletado_em": coletado_em}, upsert=True,
        )

    print(f"\nOK: {colecao.count_documents({})} registros em {BANCO}.ArboviroseBairroAnual")
    print(f"Descartados = CLASSI_FIN {DESCARTADO}. Se algum arquivo mostrar outro padrão de")
    print("classificação (o zika pode usar códigos diferentes), me avise antes de usar o mapa.")


if __name__ == "__main__":
    main()