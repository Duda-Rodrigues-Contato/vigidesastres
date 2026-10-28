"""Inspeção da API do CEMADEN (PED) antes de montar o conector.

Mostra só metadado de estação e formato de resposta; nenhum dado pessoal.
São 6 requisições: abaixo do limite de 12 por minuto para usuário externo.

Uso:
    python analises/exploracao/inspecionar_cemaden.py
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from etl.comum.texto import normalizar  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
TOKEN_URL = "https://ped.cemaden.gov.br/SGAA/rest/controle-token/tokens"
API = "https://sws.cemaden.gov.br/PED/rest"


def amostra(r):
    """Status e um pedaço do corpo, para ver o formato sem despejar tudo."""
    texto = r.text.strip()
    try:
        dados = r.json()
        if isinstance(dados, list):
            return f"{r.status_code} | lista com {len(dados)} itens | 1º item: {json.dumps(dados[0], ensure_ascii=False)[:400] if dados else '-'}"
        return f"{r.status_code} | {json.dumps(dados, ensure_ascii=False)[:500]}"
    except ValueError:
        return f"{r.status_code} | {texto[:500]}"


email, senha = os.getenv("CEMADEN_EMAIL"), os.getenv("CEMADEN_SENHA")
if not (email and senha):
    sys.exit("Preencha CEMADEN_EMAIL e CEMADEN_SENHA no .env")

r = requests.post(TOKEN_URL, json={"email": email, "password": senha}, timeout=20)
token = r.json().get("token") if r.ok else None
print("1. token:", "OK" if token else f"FALHOU {r.status_code} {r.text[:200]}")
if not token:
    sys.exit()
h = {"accept": "application/json", "token": token}

# 2. leituras recentes de PE, filtrando o Recife
r = requests.get(f"{API}/pcds/pcds-dados-recentes", headers=h,
                 params={"rede": "11", "sensor": "10", "uf": "PE"}, timeout=60)
dados = r.json() if r.ok else []
print(f"\n2. pcds-dados-recentes PE: {r.status_code} | {len(dados)} leituras")
if dados:
    print("   campos:", list(dados[0]))
    recife = {}
    for d in dados:
        if normalizar(d.get("cidade") or "") == "RECIFE":
            recife.setdefault(d["codestacao"], d)
    print(f"   estações no Recife: {len(recife)}")
    for cod, d in sorted(recife.items(), key=lambda x: x[1].get("nome") or ""):
        print(f"     {cod:<10} {str(d.get('nome'))[:38]:<38} {d.get('latitude')}, {d.get('longitude')} | último {d.get('datahora')}")
    codigo = next(iter(recife), None)
else:
    print("  ", amostra(r))
    codigo = None

time.sleep(6)
for n, (rota, params) in enumerate([
    ("pcds-acum/acumulados-recentes", {"rede": "11", "uf": "PE"}),
    ("pcds-cadastro/estacoes", {"rede": "11", "uf": "PE"}),
    ("pcds-tipo-estacao/sensores", {"rede": "11"}),
], start=3):
    r = requests.get(f"{API}/{rota}", headers=h, params=params, timeout=60)
    print(f"\n{n}. {rota}: {amostra(r)}")
    time.sleep(6)

# 6. histórico de uma estação do Recife (CSV), últimos 2 dias
if codigo:
    fim = datetime.now(timezone.utc)
    ini = fim - timedelta(days=2)
    r = requests.get(f"{API}/pcds/dados_pcd", headers={"accept": "text/csv", "token": token},
                     params={"rede": "11", "uf": "PE", "sensor": "10", "codigo": codigo,
                             "inicio": f"{ini:%Y%m%d}0000", "fim": f"{fim:%Y%m%d}2359"}, timeout=120)
    linhas = r.text.strip().splitlines()
    print(f"\n6. dados_pcd {codigo}: {r.status_code} | {len(linhas)} linhas")
    for l in linhas[:4]:
        print("  ", l[:200])
