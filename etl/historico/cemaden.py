"""Chuva histórica dos pluviômetros do CEMADEN no Recife, 2014-2024 (etapa 3b do ML).

A API entrega no máximo 31 dias por estação a cada requisição, com limite de
12 requisições por minuto: 24 estações x 132 meses = ~3.200 requisições,
umas 5 horas. Roda uma vez, de preferência à noite, e pode ser interrompida.

  silver  silver.chuva_estacao_dia   uma linha por estação e dia (dia local do Recife)

Por que diário e não cada leitura: 11 anos de leituras de 10 minutos passariam
de 3 milhões de documentos (acima do plano gratuito do Atlas). O modelo usa
chuva por dia (24 h, 72 h, 7 dias) e a maior chuva numa hora do dia (intensidade).

Uso:
    python -m etl.historico.cemaden                      # 2014-01 a 2024-12, todas as estações
    python -m etl.historico.cemaden --inicio 2020-01 --fim 2020-12
"""

import argparse
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import requests

from etl.comum.cemaden import FONTE, ClienteCemaden, ler_serie
from etl.destinos import obter_destino
from etl.destinos.base import Carga
from etl.fontes.cemaden import CODIBGE_RECIFE, UF, _hora_fechada, _numero

RECIFE = timezone(timedelta(hours=-3))  # o Recife não teve horário de verão de 2014 a 2024
TABELA = "silver.chuva_estacao_dia"
CONTROLE = "controle_historico"
TENTATIVAS = 3
ESPERA_ERRO_S = 15  # o servidor do CEMADEN devolve erro 500 de vez em quando, sem motivo aparente


def meses(inicio, fim):
    """[(ano, mes)] de inicio a fim, inclusive. inicio e fim no formato 'AAAA-MM'."""
    a, m = map(int, inicio.split("-"))
    fa, fm = map(int, fim.split("-"))
    while (a, m) <= (fa, fm):
        yield a, m
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)


def por_dia(texto, codestacao, coletado_em):
    """CSV de um mês -> uma linha por dia local: chuva total, maior chuva numa hora, nº de leituras."""
    total, por_hora, leituras = defaultdict(float), defaultdict(float), defaultdict(int)
    for l in ler_serie(texto):
        valor = _numero(l.get("valor"))
        if valor is None:
            continue
        dt = datetime.strptime(l["datahora"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        # a leitura das 00:10 é chuva de 00:00-00:10: recua 1 min antes de decidir o dia
        dia = (dt - timedelta(minutes=1)).astimezone(RECIFE).date()
        total[dia] += valor
        leituras[dia] += 1
        por_hora[(dia, _hora_fechada(dt))] += valor
    maior = defaultdict(float)
    for (dia, _), v in por_hora.items():
        maior[dia] = max(maior[dia], v)
    return [{"codestacao": codestacao, "data": datetime(d.year, d.month, d.day), "ano": d.year,
             "chuva_mm": round(total[d], 1), "max_hora_mm": round(maior[d], 1), "leituras": leituras[d],
             "fonte": FONTE, "coletado_em": coletado_em} for d in sorted(total)]


def baixar_mes(cliente, codestacao, ini, fim, espera=ESPERA_ERRO_S):
    """CSV de um mês. Tenta de novo nos erros do servidor; devolve None se todas falharem."""
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            return cliente.serie_csv(codestacao, UF, ini, fim)
        except requests.RequestException:
            if tentativa < TENTATIVAS:
                time.sleep(espera)
    return None


def janela_do_mes(ano, mes):
    """O mês LOCAL do Recife em UTC: do dia 1 às 00:00 local (03:00 UTC) até o último minuto local do mês.

    Pedir o mês em UTC cortaria o último dia local: as 3 últimas horas dele (21h-24h)
    viriam no pedido do mês seguinte, e o upsert apagaria as outras 21.
    """
    ini = datetime(ano, mes, 1, tzinfo=RECIFE)
    seguinte = datetime(ano + (mes == 12), mes % 12 + 1, 1, tzinfo=RECIFE)
    return ini.astimezone(timezone.utc), (seguinte - timedelta(minutes=1)).astimezone(timezone.utc)


def carregar(destino, cliente, inicio, fim, so_estacao=None, avisar=print, espera=ESPERA_ERRO_S):
    banco = destino.banco
    # só o que deu certo conta como feito; mês que falhou é tentado de novo na próxima rodada
    feitos = {(c["codestacao"], c["mes"]) for c in banco[CONTROLE].find({"fonte": "cemaden", "status": {"$ne": "falha"}})}
    estacoes = [e["codestacao"] for e in cliente.estacoes_do_municipio(CODIBGE_RECIFE, UF)]
    if so_estacao:
        estacoes = [e for e in estacoes if e == so_estacao]
    pendentes = [(e, a, m) for e in estacoes for a, m in meses(inicio, fim) if (e, f"{a}-{m:02d}") not in feitos]
    avisar(f"{len(estacoes)} estações, {len(pendentes)} meses pendentes "
           f"(~{len(pendentes) * 5.5 / 3600:.1f} h pelo limite de 12 requisições/min)")
    falhas = 0
    for n, (codestacao, ano, mes) in enumerate(pendentes, start=1):
        ini, fim_mes = janela_do_mes(ano, mes)
        agora = datetime.now(timezone.utc)
        texto = baixar_mes(cliente, codestacao, ini, fim_mes, espera)
        chave = {"fonte": "cemaden", "codestacao": codestacao, "mes": f"{ano}-{mes:02d}"}
        if texto is None:
            falhas += 1
            banco[CONTROLE].update_one(chave, {"$set": {"status": "falha", "em": agora}}, upsert=True)
            continue
        linhas = por_dia(texto, codestacao, agora)
        if linhas:
            destino.carregar(Carga(TABELA, linhas, chaves=("codestacao", "data")))
        banco[CONTROLE].update_one(chave, {"$set": {"status": "ok", "dias": len(linhas), "em": agora}}, upsert=True)
        if n % 12 == 0 or n == len(pendentes):
            avisar(f"  {n}/{len(pendentes)}  último: {codestacao} {ano}-{mes:02d} "
                   f"({len(linhas)} dias com leitura) | falhas até agora: {falhas}")
    if falhas:
        avisar(f"{falhas} meses falharam por erro do servidor do CEMADEN. Rode o mesmo comando de novo "
               "para tentar só esses.")


def main():
    p = argparse.ArgumentParser(description="Carga histórica do CEMADEN (retomável).")
    p.add_argument("--inicio", default="2014-01")
    p.add_argument("--fim", default="2024-12")
    p.add_argument("--estacao", help="só uma estação (código), para testar")
    a = p.parse_args()
    try:
        carregar(obter_destino(), ClienteCemaden(), a.inicio, a.fim, a.estacao, lambda s: print(s, flush=True))
    except KeyboardInterrupt:
        print("\nInterrompido. Rode o mesmo comando para continuar de onde parou.")


if __name__ == "__main__":
    main()
