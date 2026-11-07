"""Índice de vulnerabilidade por bairro: quais bairros sofrem mais com a mesma chuva? (etapa 4b)

Dois blocos, cada um de 0 a 1 (posição relativa entre os 94 bairros):

  estrutural  o que o território É (cadastros, sem olhar o histórico):
              % da população em Comunidades de Interesse Social (2014),
              risco médio dessas comunidades (alagamento e deslizamento, notas 0-10),
              áreas de risco R3/R4 do Plano de Contingência 2024
  histórico   o que o território VIVEU: atendimentos da Defesa Civil ligados à chuva
              por 10 mil habitantes, nos dias de chuva forte do seu distrito (2015-2024).
              "Com a mesma chuva": comparar só dias de chuva forte tira o efeito de
              um distrito simplesmente chover mais que o outro.

  índice = média dos dois blocos. Classe: alta (20% mais vulneráveis), média (40% seguintes), baixa.
  A correlação entre os blocos é a validação: o cadastro estrutural explica quem sofre?

  gold  gold.vulnerabilidade_bairro

Uso:
    python -m etl.derivados.vulnerabilidade
"""

import statistics
from collections import defaultdict
from datetime import datetime, timezone

from dominio import limiares
from etl.comum.texto import normalizar
from etl.derivados.ml_distrito_dia import APELIDOS_DC
from etl.destinos import obter_destino
from etl.destinos.base import Carga

ANOS = range(2015, 2025)  # 2014 fica de fora: o alvo da Defesa Civil é incompleto nele (decisão 009)


def posicao(valores):
    """{chave: posição relativa de 0 a 1} (empates ficam com a média); None fica de fora."""
    validos = sorted((v, k) for k, v in valores.items() if v is not None)
    if len(validos) < 2:
        return {k: 0.5 for k, _ in validos}
    res, i = {}, 0
    while i < len(validos):
        j = i
        while j + 1 < len(validos) and validos[j + 1][0] == validos[i][0]:
            j += 1
        for _, k in validos[i:j + 1]:
            res[k] = round(((i + j) / 2) / (len(validos) - 1), 4)
        i = j + 1
    return res


def calcular(bairros, comunidades, areas, atendimentos_fortes, dias_fortes):
    """bairros {chave: {nome, populacao, distrito_codigo}}; comunidades [{chave_bairro, populacao_2014, indicadores}];
    areas {chave: n}; atendimentos_fortes {chave: n}; dias_fortes {distrito: n}."""
    pop_cis, risco_cis = defaultdict(float), defaultdict(list)
    for c in comunidades:
        chave = c.get("chave_bairro")
        pop_cis[chave] += c.get("populacao_2014") or 0
        ind = c.get("indicadores") or {}
        notas = [v for v in (ind.get("IND_ALAGAM"), ind.get("DENS_ESCOR")) if v is not None]
        if notas:
            risco_cis[chave].append(max(notas))

    comp = {}
    for chave, b in bairros.items():
        pop = b.get("populacao") or 0
        n_dias = dias_fortes.get(b.get("distrito_codigo"), 0)
        comp[chave] = {
            "pct_pop_comunidades": round(min(1.0, pop_cis[chave] / pop), 3) if pop else None,
            "risco_comunidades": round(statistics.mean(risco_cis[chave]), 2) if risco_cis[chave] else 0.0,
            "areas_risco": areas.get(chave, 0),
            "atendimentos_10k_por_dia_forte": (round(atendimentos_fortes.get(chave, 0) / n_dias / pop * 10_000, 3)
                                               if pop and n_dias else None),
        }
    ranks = {nome: posicao({k: c[nome] for k, c in comp.items()})
             for nome in ("pct_pop_comunidades", "risco_comunidades", "areas_risco", "atendimentos_10k_por_dia_forte")}

    linhas = []
    for chave, b in bairros.items():
        partes = [ranks[n].get(chave) for n in ("pct_pop_comunidades", "risco_comunidades", "areas_risco")]
        partes = [p for p in partes if p is not None]
        estrutural = round(sum(partes) / len(partes), 3) if partes else None
        historico = ranks["atendimentos_10k_por_dia_forte"].get(chave)
        blocos = [x for x in (estrutural, historico) if x is not None]
        linhas.append({"chave": chave, "bairro": b["nome"], "distrito_codigo": b.get("distrito_codigo"),
                       "populacao": b.get("populacao"), **comp[chave],
                       "indice_estrutural": estrutural, "indice_historico": historico,
                       "indice": round(sum(blocos) / len(blocos), 3) if blocos else None})
    ordem = sorted((l for l in linhas if l["indice"] is not None), key=lambda l: -l["indice"])
    corte_alta = max(1, round(len(ordem) * 0.2))
    for i, l in enumerate(ordem, start=1):
        l["posicao"] = i
        l["classe"] = "alta" if i <= corte_alta else ("média" if i <= 3 * corte_alta else "baixa")
    return linhas


def carregar(destino, avisar=print):
    banco = destino.banco
    bairros = {b["chave"]: b for b in banco["silver_bairros"].find({}, {"geometria": 0})}
    comunidades = list(banco["silver_comunidades"].find({}, {"chave_bairro": 1, "populacao_2014": 1, "indicadores": 1}))
    areas = {a["chave"]: a.get("total_areas", 0) for a in banco["silver_areas_risco"].find({}, {"chave": 1, "total_areas": 1})}

    # dias de chuva forte de cada distrito (pior pluviômetro do distrito, tabela do modelo)
    fortes, dias_fortes = set(), defaultdict(int)
    for l in banco["gold_ml_distrito_dia"].find({"ano": {"$in": list(ANOS)},
                                                  "chuva_dia_mm": {"$gte": limiares.CHUVA_FORTE}},
                                                 {"distrito_codigo": 1, "data": 1}):
        fortes.add((l["distrito_codigo"], l["data"].date()))
        dias_fortes[l["distrito_codigo"]] += 1
    if not fortes:
        raise ValueError("gold_ml_distrito_dia vazia: rode antes python -m etl.derivados.ml_distrito_dia")

    atendimentos = defaultdict(int)
    for d in banco["silver_defesa_civil_bairro_dia"].find({"ano": {"$in": list(ANOS)}, "chuva": {"$gt": 0}},
                                                          {"data": 1, "bairro": 1, "chuva": 1}):
        chave = APELIDOS_DC.get(normalizar(d["bairro"]), normalizar(d["bairro"]))
        if chave in bairros and (bairros[chave].get("distrito_codigo"), d["data"].date()) in fortes:
            atendimentos[chave] += d["chuva"]

    linhas = calcular(bairros, comunidades, areas, atendimentos, dias_fortes)
    agora = datetime.now(timezone.utc)
    for l in linhas:
        l["coletado_em"] = agora
    destino.carregar(Carga("gold.vulnerabilidade_bairro", linhas, chaves=("chave",)))

    pares = [(l["indice_estrutural"], l["indice_historico"]) for l in linhas
             if l["indice_estrutural"] is not None and l["indice_historico"] is not None]
    corr = statistics.correlation(*zip(*pares), method="ranked") if len(pares) > 2 else float("nan")
    avisar(f"{len(linhas)} bairros | dias de chuva forte por distrito: {dict(sorted(dias_fortes.items()))}")
    avisar(f"validação: correlação estrutural x histórico = {corr:+.2f} (o cadastro explica quem sofre?)")
    avisar("10 mais vulneráveis:")
    for l in sorted(linhas, key=lambda l: l.get("posicao") or 999)[:10]:
        avisar(f"  {l['posicao']:>2}. {l['bairro']:<28} índice {l['indice']:.2f} "
               f"(estrutural {l['indice_estrutural']:.2f} | histórico {l['indice_historico'] or 0:.2f})")


if __name__ == "__main__":
    carregar(obter_destino())
