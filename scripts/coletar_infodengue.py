"""
Conector InfoDengue - dengue, chikungunya e zika no Recife, por semana.

Fonte: InfoDengue (Fiocruz + FGV), https://info.dengue.mat.br
API aberta, sem chave. Os casos vem do SINAN.

Atende a historia US-ID-03 (dados epidemiologicos), para arboviroses.

O que o InfoDengue entrega alem do SINAN bruto:
  - casos_est: estimativa CORRIGIDA PELO ATRASO DE NOTIFICACAO. A semana
    mais recente sempre parece quase vazia, porque as fichas ainda estao
    chegando - no teste, 25 casos notificados contra 253 estimados.
  - nivel de alerta de 1 (verde) a 4 (vermelho)

Limites:
  - granularidade MUNICIPAL (o Recife inteiro), nao por distrito
  - SEMANAL: a semana mais recente costuma estar 1 a 2 semanas atras de hoje
  - nao cobre escorpionismo nem leptospirose (esses so pelo SINAN bruto)

Padrao dos conectores do Vigidesastres:
  1. raw antes de normalizar
  2. `coletado_em` em todo documento
  3. buscar / normalizar / gravar separados
  4. gravacao idempotente: upsert por (doenca, semana) - as estimativas das
     semanas recentes sao revistas toda semana, e o upsert atualiza

Uso:
    python scripts/coletar_infodengue.py
"""

import os
import sys
import time
from datetime import datetime, timezone

import certifi
import requests
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.server_api import ServerApi

load_dotenv()

URL = "https://info.dengue.mat.br/api/alertcity"
GEOCODE_RECIFE = 2611606  # IBGE com digito verificador (o CNES usa sem)
DOENCAS = ["dengue", "chikungunya", "zika"]

BANCO = "Recife"
COL_RAW = "raw_infodengue"
COL = "ArboviroseSemanal"

HEADERS = {"User-Agent": "Vigidesastres/0.1 (projeto academico CESAR School)"}


def conectar():
    uri = os.getenv("MONGO_URI")
    if not uri:
        sys.exit("ERRO: MONGO_URI nao encontrada. Confira o .env")
    cliente = MongoClient(uri, server_api=ServerApi("1"), tlsCAFile=certifi.where())
    cliente.admin.command("ping")
    return cliente


def buscar(doenca, ano_inicio, ano_fim, tentativas=3):
    """Todas as semanas epidemiologicas do intervalo de anos."""
    parametros = {
        "geocode": GEOCODE_RECIFE,
        "disease": doenca,
        "format": "json",
        "ew_start": 1,
        "ew_end": 53,
        "ey_start": ano_inicio,
        "ey_end": ano_fim,
    }
    for tentativa in range(1, tentativas + 1):
        try:
            r = requests.get(URL, params=parametros, headers=HEADERS, timeout=60)
            r.raise_for_status()
            dados = r.json()
            # em caso de erro a API devolve uma mensagem, nao uma lista
            if not isinstance(dados, list):
                sys.exit(f"ERRO: resposta inesperada para {doenca}: {str(dados)[:200]}")
            return dados
        except requests.RequestException as erro:
            if tentativa == tentativas:
                raise
            espera = 2**tentativa
            print(f"  falha ({erro}); nova tentativa em {espera}s...")
            time.sleep(espera)


def _inicio_semana(valor):
    """data_iniSE vem em milissegundos no JSON (texto 'AAAA-MM-DD' no CSV)."""
    if isinstance(valor, (int, float)):
        return datetime.fromtimestamp(valor / 1000, tz=timezone.utc)
    return datetime.fromisoformat(str(valor)[:10]).replace(tzinfo=timezone.utc)


def normalizar(doenca, registros, coletado_em):
    linhas = []
    for r in registros:
        se = int(r["SE"])
        linhas.append(
            {
                "doenca": doenca,
                "se": se,  # AAAASS, ex.: 202640 = semana 40 de 2026
                "ano": se // 100,
                "semana": se % 100,
                "inicio_semana": _inicio_semana(r["data_iniSE"]),
                "casos": r.get("casos"),  # notificados ate agora
                "casos_est": r.get("casos_est"),  # corrigido pelo atraso
                "casos_est_min": r.get("casos_est_min"),
                "casos_est_max": r.get("casos_est_max"),
                "nivel": r.get("nivel"),  # 1 verde .. 4 vermelho
                "rt": r.get("Rt"),
                "p_rt1": r.get("p_rt1"),  # probabilidade de Rt > 1
                "incidencia_100k": r.get("p_inc100k"),
                "receptivo": r.get("receptivo"),
                "transmissao": r.get("transmissao"),
                "populacao": r.get("pop"),
                "notificados_no_ano": r.get("notif_accum_year"),
                "versao_modelo": r.get("versao_modelo"),
                "fonte": "infodengue",
                "coletado_em": coletado_em,
            }
        )
    return linhas


def gravar(cliente, brutos, linhas, coletado_em):
    banco = cliente[BANCO]
    banco[COL_RAW].insert_many(
        [
            {"fonte": "infodengue", "doenca": d, "coletado_em": coletado_em, "registros": regs}
            for d, regs in brutos.items()
        ]
    )
    print(f"\nRAW gravado em {BANCO}.{COL_RAW}")

    colecao = banco[COL]
    colecao.create_index([("doenca", 1), ("se", 1)], unique=True, name="idx_doenca_se")
    resultado = colecao.bulk_write(
        [
            UpdateOne({"doenca": l["doenca"], "se": l["se"]}, {"$set": l}, upsert=True)
            for l in linhas
        ]
    )
    print(
        f"OK: {resultado.upserted_count} semanas novas, "
        f"{resultado.modified_count} atualizadas "
        f"({colecao.count_documents({})} no total em {BANCO}.{COL})"
    )


NOMES_NIVEL = {1: "verde", 2: "amarelo", 3: "laranja", 4: "vermelho"}


def resumo(linhas):
    print(f"\n{'doenca':<12} {'semana':>7} {'notificados':>12} {'estimados':>10} {'intervalo':>13}  nivel")
    for doenca in DOENCAS:
        da_doenca = [l for l in linhas if l["doenca"] == doenca]
        if not da_doenca:
            print(f"{doenca:<12} sem dados")
            continue
        u = max(da_doenca, key=lambda l: l["se"])
        intervalo = f"{u['casos_est_min']:.0f}-{u['casos_est_max']:.0f}" if u["casos_est_min"] is not None else "--"
        print(
            f"{doenca:<12} {u['se']:>7} {u['casos'] or 0:>12} {u['casos_est'] or 0:>10.0f} "
            f"{intervalo:>13}  {u['nivel']} ({NOMES_NIVEL.get(u['nivel'], '?')})"
        )


def main():
    coletado_em = datetime.now(timezone.utc)
    ano = coletado_em.year

    brutos, linhas = {}, []
    for doenca in DOENCAS:
        print(f"Consultando InfoDengue: {doenca} ({ano - 1}-{ano})...")
        brutos[doenca] = buscar(doenca, ano - 1, ano)
        linhas += normalizar(doenca, brutos[doenca], coletado_em)

    if not linhas:
        sys.exit("ERRO: o InfoDengue nao devolveu nenhuma semana.")

    gravar(conectar(), brutos, linhas, coletado_em)
    resumo(linhas)
    print(f"\nColeta de {coletado_em.isoformat()} concluida.")


if __name__ == "__main__":
    main()