"""
Conector CNES - unidades de saude do Recife.

Fonte: API de Dados Abertos do Ministerio da Saude
https://apidadosabertos.saude.gov.br

Atende a historia US-ID-04 (dados assistenciais).

Padrao adotado em todos os conectores do Vigidesastres:
  1. a resposta original vai para uma colecao `raw_*` antes de qualquer
     transformacao
  2. todo documento carrega `coletado_em`
  3. buscar / normalizar / gravar sao funcoes separadas

Uso:
    python scripts/coletar_cnes.py            # so unidades de resposta
    python scripts/coletar_cnes.py --todos    # todos os estabelecimentos
    python scripts/coletar_cnes.py --tipos    # lista os tipos e sai
"""

import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone

import certifi
import requests
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()

BASE = "https://apidadosabertos.saude.gov.br/cnes"
CODIGO_MUNICIPIO_RECIFE = 261160
TAMANHO_PAGINA = 20  # a API ignora limit maior e devolve 20
MAX_PAGINAS = 1000

BANCO = "Recife"
COLECAO_RAW = "raw_cnes_estabelecimentos"
COLECAO = "UnidadesSaude"

HEADERS = {
    "User-Agent": "Vigidesastres/0.1 (projeto academico CESAR School)",
    "Accept": "application/json",
}

# Tipos que importam numa emergencia climatica: quem atende, interna
# ou se desloca. Fica de fora consultorio isolado, laboratorio privado,
# farmacia e afins - a maior parte do cadastro, que poluiria o mapa
# sem ajudar na decisao.
TIPOS_RESPOSTA = {
    1,  # POSTO DE SAUDE
    2,  # CENTRO DE SAUDE/UNIDADE BASICA (UBS)
    4,  # POLICLINICA
    5,  # HOSPITAL GERAL
    7,  # HOSPITAL ESPECIALIZADO
    15,  # UNIDADE MISTA
    20,  # PRONTO SOCORRO GERAL
    21,  # PRONTO SOCORRO ESPECIALIZADO
    40,  # UNIDADE MOVEL TERRESTRE
    42,  # UNIDADE MOVEL PRE-HOSPITALAR (SAMU)
    50,  # UNIDADE DE VIGILANCIA EM SAUDE (estrutura do Vigidesastres)
    61,  # CENTRO DE PARTO NORMAL
    62,  # HOSPITAL/DIA
    69,  # CENTRO DE ATENCAO HEMOTERAPIA
    70,  # CENTRO DE ATENCAO PSICOSSOCIAL (CAPS)
    71,  # CENTRO DE APOIO A SAUDE DA FAMILIA
    73,  # PRONTO ATENDIMENTO (UPA)
    85,  # CENTRO DE IMUNIZACAO (resposta pos-inundacao)
}


def buscar(caminho, parametros, tentativas=3):
    """GET com retry e backoff. Levanta a excecao na ultima tentativa."""
    for tentativa in range(1, tentativas + 1):
        try:
            r = requests.get(
                f"{BASE}/{caminho}", params=parametros, headers=HEADERS, timeout=30
            )
            r.raise_for_status()
            return r.json()
        except requests.RequestException as erro:
            if tentativa == tentativas:
                raise
            espera = 2**tentativa
            print(f"  falha ({erro}); nova tentativa em {espera}s...")
            time.sleep(espera)


def mapa_de_tipos():
    """codigo -> descricao, direto da API (evita chutar codigo)."""
    dados = buscar("tipounidades", {"limit": 200})
    return {
        t["codigo_tipo_unidade"]: t["descricao_tipo_unidade"]
        for t in dados.get("tipos_unidade", [])
    }


def buscar_estabelecimentos():
    print(f"Buscando estabelecimentos do municipio {CODIGO_MUNICIPIO_RECIFE}...")
    todos = []
    completou = False

    for pagina in range(MAX_PAGINAS):
        dados = buscar(
            "estabelecimentos",
            {
                "codigo_municipio": CODIGO_MUNICIPIO_RECIFE,
                "limit": TAMANHO_PAGINA,
                "offset": pagina * TAMANHO_PAGINA,
            },
        )
        lote = dados.get("estabelecimentos", [])

        if not lote:
            completou = True
            break

        if pagina == 0 and len(lote) < TAMANHO_PAGINA:
            print(
                f"  aviso: pedi {TAMANHO_PAGINA} por pagina e vieram {len(lote)}.\n"
                f"  Ajustando o tamanho de pagina para {len(lote)}."
            )

        todos.extend(lote)
        if pagina % 25 == 0:
            print(f"  pagina {pagina + 1}: total {len(todos)}")

        # so considera fim de lista quando a pagina volta vazia;
        # a API pode devolver menos itens do que o limit pedido
        if len(lote) == 0:
            completou = True
            break

    if not completou:
        print(
            f"\n  ATENCAO: parou em {MAX_PAGINAS} paginas (trava de seguranca).\n"
            "  A coleta esta incompleta - aumente MAX_PAGINAS."
        )

    print(f"Total coletado: {len(todos)}")
    return todos


def resumir_tipos(estabelecimentos, tipos):
    """Distribuicao por tipo - ajuda a decidir o que entra no mapa."""
    contagem = Counter(e.get("codigo_tipo_unidade") for e in estabelecimentos)

    print(f"\n{'cod':>4}  {'qtd':>5}  {'resposta':>8}  tipo")
    for codigo, qtd in contagem.most_common():
        marca = "sim" if codigo in TIPOS_RESPOSTA else "-"
        nome = tipos.get(codigo, "?")
        print(f"{str(codigo):>4}  {qtd:>5}  {marca:>8}  {nome[:48]}")


def normalizar(estabelecimentos, tipos, coletado_em):
    unidades = []

    for e in estabelecimentos:
        lat = e.get("latitude_estabelecimento_decimo_grau")
        lon = e.get("longitude_estabelecimento_decimo_grau")
        codigo_tipo = e.get("codigo_tipo_unidade")

        unidades.append(
            {
                "codigo_cnes": e.get("codigo_cnes"),
                "nome": e.get("nome_fantasia") or e.get("nome_razao_social"),
                "bairro": e.get("bairro_estabelecimento"),
                "endereco": e.get("endereco_estabelecimento"),
                "codigo_tipo": codigo_tipo,
                "tipo": tipos.get(codigo_tipo),
                "atende_hospitalar": e.get(
                    "estabelecimento_possui_atendimento_hospitalar"
                ),
                "turno": e.get("descricao_turno_atendimento"),
                # GeoJSON Point e [lon, lat], nessa ordem
                "localizacao": (
                    {"type": "Point", "coordinates": [float(lon), float(lat)]}
                    if lat is not None and lon is not None
                    else None
                ),
                "atualizado_na_fonte": e.get("data_atualizacao"),
                "coletado_em": coletado_em,
            }
        )

    return unidades


def conectar():
    uri = os.getenv("MONGO_URI")
    if not uri:
        sys.exit("ERRO: MONGO_URI nao encontrada. Confira o .env")
    cliente = MongoClient(uri, server_api=ServerApi("1"), tlsCAFile=certifi.where())
    cliente.admin.command("ping")
    return cliente


def gravar(cliente, cadastro_completo, unidades, coletado_em):
    banco = cliente[BANCO]

    # RAW: um documento por estabelecimento. Tudo num unico documento
    # estouraria o limite de 16 MB do BSON conforme a base cresce.
    raw = banco[COLECAO_RAW]
    raw.delete_many({})
    raw.insert_many(
        [
            {"fonte": "cnes", "coletado_em": coletado_em, "registro": r}
            for r in cadastro_completo
        ]
    )
    print(f"\nRAW: {raw.count_documents({})} registros em {BANCO}.{COLECAO_RAW}")

    # Normalizado: o que a aplicacao consome
    colecao = banco[COLECAO]
    colecao.drop()  # recria do zero: evita conflito de indice entre execucoes
    colecao.insert_many(unidades)
    colecao.create_index("codigo_cnes", name="idx_cnes")
    colecao.create_index("codigo_tipo", name="idx_tipo")
    colecao.create_index([("localizacao", "2dsphere")], name="idx_geo")

    print(f"OK: {colecao.count_documents({})} unidades em {BANCO}.{COLECAO}")


def main():
    apenas_resposta = "--todos" not in sys.argv
    coletado_em = datetime.now(timezone.utc)

    tipos = mapa_de_tipos()
    print(f"{len(tipos)} tipos de unidade no catalogo CNES.\n")

    if "--tipos" in sys.argv:
        for codigo, nome in sorted(tipos.items()):
            print(f"{codigo:>4}  {nome}")
        return

    cadastro_completo = buscar_estabelecimentos()
    if not cadastro_completo:
        sys.exit("ERRO: a API nao devolveu nenhum estabelecimento.")

    resumir_tipos(cadastro_completo, tipos)

    # O RAW guarda SEMPRE o cadastro completo, mesmo quando a colecao
    # normalizada fica so com as unidades de resposta. Assim, mudar o
    # recorte depois nao exige recoletar da API.
    if apenas_resposta:
        selecionados = [
            e
            for e in cadastro_completo
            if e.get("codigo_tipo_unidade") in TIPOS_RESPOSTA
        ]
        print(
            f"\nUnidades de resposta: {len(selecionados)} de "
            f"{len(cadastro_completo)} (use --todos para o cadastro completo)"
        )
    else:
        selecionados = cadastro_completo

    unidades = normalizar(selecionados, tipos, coletado_em)

    sem_coord = sum(1 for u in unidades if u["localizacao"] is None)
    if sem_coord:
        pct = 100 * sem_coord / len(unidades)
        print(f"  {sem_coord} sem coordenada ({pct:.0f}%) - nao aparecem no mapa")

    cliente = conectar()
    gravar(cliente, cadastro_completo, unidades, coletado_em)

    print(f"\nColeta de {coletado_em.isoformat()} concluida.")


if __name__ == "__main__":
    main()