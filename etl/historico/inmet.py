"""Chuva histórica da estação automática do INMET no Recife (A301), 2014-2024 (etapa 3b do ML).

Fonte: pacotes anuais abertos do INMET (portal.inmet.gov.br/dadoshistoricos),
um ZIP por ano com um CSV por estação do Brasil. Baixa o ano, guarda só a
estação do Recife e descarta o resto. Sem cadastro, sem token.

  silver  silver.chuva_inmet_dia   uma linha por dia local do Recife

Serve para conferir o CEMADEN e para preencher os dias em que os pluviômetros
ainda não existiam ou estavam parados. Os CSVs mudam de formato entre os anos
(data com / ou -, hora "0000" ou "0000 UTC", vírgula decimal, -9999 = sem dado):
a leitura cobre todos esses casos.

Uso:
    python -m etl.historico.inmet                 # 2014 a 2024
    python -m etl.historico.inmet --inicio 2024 --fim 2024
"""

import argparse
import csv
import io
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from etl.comum.http import get_bytes
from etl.comum.tabela import decodificar
from etl.destinos import obter_destino
from etl.destinos.base import Carga

URL = "https://portal.inmet.gov.br/uploads/dadoshistoricos/{ano}.zip"
ESTACAO = "A301"  # Recife (automática)
RECIFE = timezone(timedelta(hours=-3))
TABELA = "silver.chuva_inmet_dia"
CONTROLE = "controle_historico"
FONTE = "INMET, estação automática A301 Recife"


def csv_da_estacao(conteudo_zip, estacao=ESTACAO):
    """O texto do CSV da estação dentro do ZIP do ano; None se não houver."""
    with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as z:
        nome = next((n for n in z.namelist() if f"_{estacao}_" in n.upper()), None)
        return decodificar(z.read(nome)) if nome else None


def _numero(v):
    try:
        x = float(str(v).strip().replace(",", "."))
    except ValueError:
        return None
    return None if x <= -9999 else x


def _quando(data, hora):
    """'2014/01/01' ou '2019-01-01' + '1200' ou '1200 UTC' ou '12:00' -> datetime UTC."""
    d = datetime.strptime(data.strip().replace("/", "-"), "%Y-%m-%d")
    h = re.sub(r"\D", "", hora)[:4].ljust(4, "0")
    return d.replace(hour=int(h[:2]), minute=int(h[2:]), tzinfo=timezone.utc)


def por_dia(texto, coletado_em):
    """CSV horário do INMET -> uma linha por dia local: total, maior hora, horas com dado."""
    linhas = texto.splitlines()
    # o cabeçalho é a linha com a coluna de chuva (antes dela há metadados, como "DATA DE FUNDACAO")
    ini = next((i for i, l in enumerate(linhas) if "PRECIPITA" in l.upper()), None)
    if ini is None:
        return []
    leitor = csv.reader(linhas[ini + 1:], delimiter=";")
    cab = [c.strip().upper() for c in linhas[ini].split(";")]
    c_data, c_hora = 0, 1
    c_chuva = next(i for i, c in enumerate(cab) if c.startswith("PRECIPITA"))
    total, maior, horas = defaultdict(float), defaultdict(float), defaultdict(int)
    for l in leitor:
        if len(l) <= c_chuva or not l[c_data].strip():
            continue
        valor = _numero(l[c_chuva])
        if valor is None:
            continue
        # a hora registrada é o FIM do intervalo: a chuva das 00 UTC é da hora anterior
        dia = (_quando(l[c_data], l[c_hora]) - timedelta(minutes=1)).astimezone(RECIFE).date()
        total[dia] += valor
        maior[dia] = max(maior[dia], valor)
        horas[dia] += 1
    return [{"data": datetime(d.year, d.month, d.day), "ano": d.year, "chuva_mm": round(total[d], 1),
             "max_hora_mm": round(maior[d], 1), "horas_com_dado": horas[d], "fonte": FONTE,
             "coletado_em": coletado_em} for d in sorted(total)]


def carregar(destino, inicio, fim, baixar=lambda ano: get_bytes(URL.format(ano=ano), timeout=600), avisar=print):
    banco = destino.banco
    feitos = {c["mes"] for c in banco[CONTROLE].find({"fonte": "inmet"})}
    for ano in range(inicio, fim + 1):
        if str(ano) in feitos:
            avisar(f"  {ano}: já carregado")
            continue
        avisar(f"  {ano}: baixando o pacote do ano (arquivo grande, alguns minutos)...")
        agora = datetime.now(timezone.utc)
        texto = csv_da_estacao(baixar(ano))
        linhas = por_dia(texto, agora) if texto else []
        if linhas:
            destino.carregar(Carga(TABELA, linhas, chaves=("data",)))
        banco[CONTROLE].update_one({"fonte": "inmet", "mes": str(ano)},
                                   {"$set": {"dias": len(linhas), "em": agora}}, upsert=True)
        completos = sum(l["horas_com_dado"] >= 20 for l in linhas)
        avisar(f"  {ano}: {len(linhas)} dias com dado ({completos} com 20 h ou mais)"
               + ("" if texto else f" | estação {ESTACAO} não está no pacote deste ano"))


def main():
    p = argparse.ArgumentParser(description="Carga histórica do INMET (retomável, por ano).")
    p.add_argument("--inicio", type=int, default=2014)
    p.add_argument("--fim", type=int, default=2024)
    a = p.parse_args()
    try:
        carregar(obter_destino(), a.inicio, a.fim, avisar=lambda s: print(s, flush=True))
    except KeyboardInterrupt:
        print("\nInterrompido. Rode o mesmo comando para continuar de onde parou.")


if __name__ == "__main__":
    main()
