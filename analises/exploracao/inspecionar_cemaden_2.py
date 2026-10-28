"""Segunda inspeção do CEMADEN: acumulados, cadastro e sensores de solo.

Mostra só metadado de estação e formato de resposta. 7 requisições, com
pausa entre elas (limite: 12 por minuto).

Uso:
    python analises/exploracao/inspecionar_cemaden_2.py
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
API = "https://sws.cemaden.gov.br/PED/rest"
r = requests.post("https://ped.cemaden.gov.br/SGAA/rest/controle-token/tokens",
                  json={"email": os.getenv("CEMADEN_EMAIL"), "password": os.getenv("CEMADEN_SENHA")}, timeout=20)
token = r.json().get("token") if r.ok else sys.exit(f"token falhou: {r.status_code}")
h = {"accept": "application/json", "token": token}


def get(rota, params):
    time.sleep(6)
    r = requests.get(f"{API}/{rota}", headers=h, params=params, timeout=60)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, r.text[:300]


# 1. todos os tipos de estação e seus sensores
_, tipos = get("pcds-tipo-estacao/sensores", {"rede": "11"})
print("1. tipos de estação e sensores:")
for t in tipos if isinstance(tipos, list) else []:
    sensores = ", ".join(f"{s['sensor']}={s['sensordescricao']}" for s in t["sensor"])
    print(f"   {t['tipoestacao']} {t['tipoestacaodescricao']}: {sensores}")

# 2 e 3. acumulados e cadastro: testa o código IBGE com 7 e com 6 dígitos
for rota in ("pcds-acum/acumulados-recentes", "pcds-cadastro/estacoes"):
    for codibge in ("2611606", "261160"):
        status, dados = get(rota, {"rede": "11", "uf": "PE", "codibge": codibge})
        if status == 200 and isinstance(dados, list) and dados:
            print(f"\n{rota} codibge={codibge}: {len(dados)} itens | campos: {list(dados[0])}")
            print("   1º item:", json.dumps(dados[0], ensure_ascii=False)[:500])
            break
        print(f"\n{rota} codibge={codibge}: {status} | {str(dados)[:200]}")

# 4. umidade do solo agora no Recife (sensor 330 = nível 1)
status, dados = get("pcds/pcds-dados-recentes", {"rede": "11", "sensor": "330", "uf": "PE"})
recife = sorted({(d["codestacao"], d["nome"]) for d in dados if "RECIFE" in str(d.get("cidade")).upper()}) if isinstance(dados, list) else []
print(f"\n4. umidade do solo (330) PE: {status} | {len(dados) if isinstance(dados, list) else dados}")
print("   estações do Recife com umidade do solo:", recife or "nenhuma")
if recife:
    exemplo = next(d for d in dados if d["codestacao"] == recife[0][0])
    print("   exemplo:", {k: exemplo[k] for k in ("datahora", "valor", "qualificacao", "offset")})
