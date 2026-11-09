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
    maior, pico = defaultdict(float), {}
    for (dia, hora), v in sorted(por_hora.items()):
        if v > maior[dia]:
            # a hora "fechada" termina às HH:00: a chuva caiu na hora anterior (início, em UTC)
            maior[dia], pico[dia] = v, (hora - timedelta(hours=1)).replace(tzinfo=None)
    return [{"codestacao": codestacao, "data": datetime(d.year, d.month, d.day), "ano": d.year,
             "chuva_mm": round(total[d], 1), "max_hora_mm": round(maior[d], 1), "leituras": leituras[d],
             "hora_pico_utc": pico.get(d), "fonte": FONTE, "coletado_em": coletado_em} for d in sorted(total)]


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
    """O mês LOCAL do Recife em UTC, no mesmo critério de por_dia().

    Cada leitura é a chuva do intervalo que TERMINA no seu horário: a das 00:00 local
    do dia 1 ainda é chuva do último dia do mês anterior. Por isso a janela começa às
    00:01 local do dia 1 e termina às 00:00 local do dia 1 do mês seguinte (inclusive).
    Assim cada dia local cai inteiro num único pedido, e nenhum pedido sobrescreve o
    último dia do mês vizinho.
    """
    ini = datetime(ano, mes, 1, 0, 1, tzinfo=RECIFE)
    fim = datetime(ano + (mes == 12), mes % 12 + 1, 1, tzinfo=RECIFE)
    return ini.astimezone(timezone.utc), fim.astimezone(timezone.utc)


def carregar(destino, cliente, inicio, fim, so_estacao=None, avisar=print, espera=ESPERA_ERRO_S, refazer=False):
    banco = destino.banco
    # só o que deu certo conta como feito; mês que falhou é tentado de novo na próxima rodada.
    # refazer: baixa de novo (por exemplo, para gravar um campo novo); marca na etiqueta do controle
    etiqueta = "cemaden_refeito" if refazer else "cemaden"
    feitos = {(c["codestacao"], c["mes"]) for c in banco[CONTROLE].find({"fonte": etiqueta, "status": {"$ne": "falha"}})}
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
        chave = {"fonte": etiqueta, "codestacao": codestacao, "mes": f"{ano}-{mes:02d}"}
        if texto is None:
            falhas += 1
            banco[CONTROLE].update_one(chave, {"$set": {"status": "falha", "em": agora}}, upsert=True)
            continue
        linhas = [l for l in por_dia(texto, codestacao, agora) if (l["data"].year, l["data"].month) == (ano, mes)]
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
    p.add_argument("--refazer", action="store_true",
                   help="baixa de novo todos os meses (retomável à parte), para gravar campos novos")
    a = p.parse_args()
    try:
        carregar(obter_destino(), ClienteCemaden(), a.inicio, a.fim, a.estacao, lambda s: print(s, flush=True),
                 refazer=a.refazer)
    except KeyboardInterrupt:
        print("\nInterrompido. Rode o mesmo comando para continuar de onde parou.")


if __name__ == "__main__":
    main()
