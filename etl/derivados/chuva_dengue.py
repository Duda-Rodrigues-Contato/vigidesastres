"""Chuva -> dengue: quantas semanas depois de um período chuvoso os casos sobem? (etapa 4c)

Séries semanais (semana epidemiológica) de 2014 a 2024:
  chuva   média diária dos 8 distritos (tabela do modelo), somada na semana
  dengue  casos estimados do InfoDengue (corrigem o atraso de notificação)

O cuidado principal: chuva e dengue têm o MESMO ciclo anual (sobem no 1º semestre).
Correlacionar as séries cruas mostra só que as duas são sazonais. Por isso a análise
usa ANOMALIAS: o quanto cada semana ficou acima ou abaixo do normal daquela semana
do ano. A pergunta vira: "um período mais chuvoso que o normal é seguido, X semanas
depois, de mais dengue que o normal?". A dengue entra em log (epidemias de anos
diferentes variam muito de tamanho). A chuva entra também acumulada em 4 semanas:
o mosquito depende de água parada, não de um dia de chuva.

  gold  gold.chuva_dengue_defasagem   uma linha por defasagem (0 a 12 semanas)

Uso:
    python -m etl.derivados.chuva_dengue
"""

import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from etl.destinos import obter_destino
from etl.destinos.base import Carga

DEFASAGENS = range(0, 13)
JANELA = 4  # semanas de chuva acumulada


def anomalias(serie):
    """{se: valor} -> {se: valor - média daquela semana do ano}."""
    por_semana = defaultdict(list)
    for se, v in serie.items():
        por_semana[se % 100].append(v)
    normal = {s: statistics.mean(v) for s, v in por_semana.items()}
    return {se: v - normal[se % 100] for se, v in serie.items()}


def correlacao(x_por_se, y_por_se, semanas, defasagem):
    """Correlação por postos entre x de `defasagem` semanas antes e y."""
    pares = [(x_por_se[semanas[i - defasagem]], y_por_se[semanas[i]])
             for i in range(defasagem, len(semanas))
             if semanas[i - defasagem] in x_por_se and semanas[i] in y_por_se]
    if len(pares) < 20:
        return None
    try:
        return round(statistics.correlation(*zip(*pares), method="ranked"), 3)
    except statistics.StatisticsError:
        return None


def calcular(chuva_semana, dengue_semana):
    """Entradas {se: valor} já alinhadas por semana epidemiológica. Devolve as linhas por defasagem."""
    semanas = sorted(set(chuva_semana) & set(dengue_semana))
    acumulada = {}
    for i, se in enumerate(semanas):
        janela = semanas[max(0, i - JANELA + 1):i + 1]
        if len(janela) == JANELA:
            acumulada[se] = sum(chuva_semana[s] for s in janela)
    dengue_log = {se: math.log1p(v) for se, v in dengue_semana.items()}
    a_chuva, a_acum, a_dengue = anomalias(chuva_semana), anomalias(acumulada), anomalias(dengue_log)
    linhas = []
    for d in DEFASAGENS:
        linhas.append({"defasagem_semanas": d,
                       "corr_bruta": correlacao(chuva_semana, dengue_log, semanas, d),
                       "corr_anomalia": correlacao(a_chuva, a_dengue, semanas, d),
                       "corr_anomalia_4sem": correlacao(a_acum, a_dengue, semanas, d)})
    return linhas


def series(banco):
    chuva_dia = defaultdict(list)
    for l in banco["gold_ml_distrito_dia"].find({"chuva_dia_mm": {"$ne": None}}, {"data": 1, "chuva_dia_mm": 1}):
        chuva_dia[l["data"].date()].append(l["chuva_dia_mm"])
    media_dia = {d: statistics.mean(v) for d, v in chuva_dia.items()}
    chuva_semana, dengue_semana = {}, {}
    for s in banco["silver_arbovirose_semanal"].find({"doenca": "dengue", "ano": {"$gte": 2014, "$lte": 2024}},
                                                     {"se": 1, "inicio_semana": 1, "casos_est": 1}):
        inicio = s["inicio_semana"].date() if hasattr(s["inicio_semana"], "date") else s["inicio_semana"]
        dias = [media_dia.get(inicio + timedelta(n)) for n in range(7)]
        if None not in dias and s.get("casos_est") is not None:
            chuva_semana[s["se"]] = round(sum(dias), 1)
            dengue_semana[s["se"]] = s["casos_est"]
    if not chuva_semana:
        raise ValueError("sem semanas com chuva e dengue: rode antes a etapa 3e e a 3d")
    return chuva_semana, dengue_semana


def carregar(destino, avisar=print):
    chuva, dengue = series(destino.banco)
    linhas = calcular(chuva, dengue)
    agora = datetime.now(timezone.utc)
    for l in linhas:
        l["semanas_analisadas"] = len(chuva)
        l["coletado_em"] = agora
    destino.carregar(Carga("gold.chuva_dengue_defasagem", linhas, chaves=("defasagem_semanas",)))
    avisar(f"{len(chuva)} semanas com chuva e dengue (2014-2024)\n")
    avisar(f"{'defasagem':>10}{'bruta':>9}{'anomalia':>11}{'anom. 4 sem':>13}")
    for l in linhas:
        avisar(f"{l['defasagem_semanas']:>7} sem{l['corr_bruta'] or 0:>9.2f}{l['corr_anomalia'] or 0:>11.2f}"
               f"{l['corr_anomalia_4sem'] or 0:>13.2f}")
    melhor = max(linhas, key=lambda l: l["corr_anomalia_4sem"] or -1)
    avisar(f"\nmaior relação (chuva acumulada em 4 semanas, sem a sazonalidade): "
           f"{melhor['defasagem_semanas']} semanas depois, correlação {melhor['corr_anomalia_4sem']:+.2f}")
    avisar("A coluna 'bruta' mistura o ciclo anual: use a de anomalia para concluir.")


if __name__ == "__main__":
    carregar(obter_destino())
