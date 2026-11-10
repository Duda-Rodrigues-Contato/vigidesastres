"""Tabela do modelo de EVENTOS: uma linha por unidade e dia, 2016 até a última chuva carregada.

Unidades: os 8 distritos do Recife e 6 municípios vizinhos (dominio/rmr.py).
Alvo: houve ocorrência no REINDESC naquela unidade e naquele dia (e de que tipo).

Entradas (tudo o que se conhece até o dia avaliado; a chuva do próprio dia, no uso
diário, vem da previsão):
  chuva    pior pluviômetro da unidade: dia, véspera, 3 e 7 dias, 72 h anteriores,
           maior chuva numa hora, e "chuva com memória" (14 dias, peso 0,85 ao dia)
  maré     nível na HORA do pico de chuva da unidade (decisão 011) e maré máxima do dia
  solo     umidade do solo do ERA5-Land na VÉSPERA, em 3 camadas
  contexto mês e unidade

  gold  gold.ml_eventos_dia

Uso:
    python -m etl.derivados.ml_eventos_dia
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from dominio.rmr import eh_recife, unidade_da_estacao, unidades
from etl.derivados.ml_distrito_dia import MIN_HORAS_INMET, MIN_LEITURAS, garantir_coordenadas
from etl.destinos import obter_destino
from etl.destinos.base import Carga

INICIO = date(2016, 1, 1)
DECAIMENTO, DIAS_MEMORIA = 0.85, 14
TABELA = "gold.ml_eventos_dia"


def _soma(serie, dia, dias):
    valores = [serie.get(dia - timedelta(n)) for n in range(dias)]
    return None if any(v is None for v in valores) else round(sum(valores), 1)


def memoria(serie, dia):
    """Índice de chuva antecedente: chuva dos 14 dias ANTERIORES, a de ontem pesando mais."""
    valores = [(serie.get(dia - timedelta(k)), DECAIMENTO ** k) for k in range(1, DIAS_MEMORIA + 1)]
    if sum(1 for v, _ in valores if v is not None) < DIAS_MEMORIA - 2:
        return None
    return round(sum(v * p for v, p in valores if v is not None), 1)


def montar(estacao_dia, unidade_estacao, inmet_dia, mare_dia, mare_hora, solo, eventos, inicio, fim):
    """Entradas (chaves date):
      estacao_dia     {(cod, dia): (chuva, max_hora, leituras, hora_pico)}
      unidade_estacao {cod: unidade}
      inmet_dia       {dia: (chuva, max_hora, horas)}  só preenche distritos do Recife
      mare_dia        {dia: mare_max_m};  mare_hora {datetime hora UTC: nivel}
      solo            {(unidade, dia): {solo_0_7cm, ...}}
      eventos         {(unidade, dia): {"n": int, "geo": int, "hidro": int, "gp": int}}
    """
    pior, pico = {}, {}
    for (cod, dia), (mm, max_h, leituras, hora_pico) in estacao_dia.items():
        unidade = unidade_estacao.get(cod)
        if unidade is None or leituras < MIN_LEITURAS:
            continue
        if (unidade, dia) not in pior or mm > pior[(unidade, dia)][0]:
            pior[(unidade, dia)] = (mm, max_h)
        if hora_pico is not None and max_h > pico.get((unidade, dia), (0, None))[0]:
            pico[(unidade, dia)] = (max_h, hora_pico)

    linhas = []
    for codigo, unidade in enumerate(unidades(), start=1):
        chuva = {}
        d = inicio - timedelta(days=DIAS_MEMORIA + 1)
        while d <= fim:
            if (unidade, d) in pior:
                chuva[d] = pior[(unidade, d)][0]
            elif eh_recife(unidade) and d in inmet_dia and inmet_dia[d][2] >= MIN_HORAS_INMET:
                chuva[d] = inmet_dia[d][0]
            d += timedelta(1)
        d = inicio
        while d <= fim:
            ev = eventos.get((unidade, d), {})
            chuva_pico, hora_pico = pico.get((unidade, d), (None, None))
            s = solo.get((unidade, d - timedelta(1)), {})
            linhas.append({
                "unidade": unidade, "unidade_codigo": codigo, "recife": eh_recife(unidade),
                "data": datetime(d.year, d.month, d.day), "ano": d.year, "mes": d.month,
                "chuva_dia_mm": chuva.get(d), "chuva_vespera_mm": chuva.get(d - timedelta(1)),
                "chuva_3d_mm": _soma(chuva, d, 3), "chuva_7d_mm": _soma(chuva, d, 7),
                "acumulado_72h_antes": _soma(chuva, d - timedelta(1), 3), "chuva_memoria": memoria(chuva, d),
                "max_hora_mm": pior.get((unidade, d), (None, None))[1], "chuva_pico_mm": chuva_pico,
                "mare_hora_pico_m": mare_hora.get(hora_pico.replace(minute=0, second=0)) if hora_pico else None,
                "mare_max_m": mare_dia.get(d),
                "solo_0_7cm_vespera": s.get("solo_0_7cm"), "solo_7_28cm_vespera": s.get("solo_7_28cm"),
                "solo_28_100cm_vespera": s.get("solo_28_100cm"),
                "evento": ev.get("n", 0) > 0, "ocorrencias": ev.get("n", 0),
                "evento_geo": ev.get("geo", 0) > 0, "evento_hidro": ev.get("hidro", 0) > 0,
                "evento_grande": ev.get("gp", 0) > 0,
            })
            d += timedelta(1)
    return linhas


def ler_entradas(banco):
    distritos = garantir_coordenadas(banco)
    unidade_estacao = {}
    for c in banco["controle_historico"].distinct("codestacao", {"fonte": {"$in": ["cemaden", "cemaden_refeito"]}}):
        u = unidade_da_estacao(c, distritos.get(c))
        if u:
            unidade_estacao[c] = u
    estacao_dia = {(e["codestacao"], e["data"].date()): (e["chuva_mm"], e["max_hora_mm"], e["leituras"],
                                                          e.get("hora_pico_utc"))
                   for e in banco["silver_chuva_estacao_dia"].find({"ano": {"$gte": INICIO.year - 1}})}
    inmet = {e["data"].date(): (e["chuva_mm"], e["max_hora_mm"], e["horas_com_dado"])
             for e in banco["silver_chuva_inmet_dia"].find()}
    mare_dia = {m["data"].date(): m["mare_max_m"] for m in banco["silver_mare_calculada_dia"].find()}
    mare_hora = {m["hora"]: m["nivel_m"] for m in banco["silver_mare_calculada_hora"].find({"hora": {"$gte": datetime(2015, 12, 1)}})}
    solo = {(s["unidade"], s["data"].date()): s for s in banco["silver_clima_era5land_dia"].find()}
    eventos = defaultdict(lambda: {"n": 0, "geo": 0, "hidro": 0, "gp": 0})
    for o in banco["silver_reindesc_ocorrencias"].find():
        e = eventos[(o["unidade"], o["data"].date())]
        e["n"] += 1
        e["geo"] += o.get("tipologia") == "Geo"
        e["hidro"] += o.get("tipologia") == "Hidro"
        e["gp"] += o.get("magnitude") == "GP"
    if not eventos:
        raise ValueError("silver_reindesc_ocorrencias vazia: rode antes python -m etl.historico.reindesc")
    fim = max(d for _, d in estacao_dia)
    return estacao_dia, unidade_estacao, inmet, mare_dia, mare_hora, solo, dict(eventos), fim


def carregar(destino, avisar=print):
    estacao_dia, unidade_estacao, inmet, mare_dia, mare_hora, solo, eventos, fim = ler_entradas(destino.banco)
    linhas = montar(estacao_dia, unidade_estacao, inmet, mare_dia, mare_hora, solo, eventos, INICIO, fim)
    agora = datetime.now(timezone.utc)
    for l in linhas:
        l["coletado_em"] = agora
    destino.carregar(Carga(TABELA, linhas, chaves=("unidade", "data")))
    avisar(f"{len(linhas)} linhas ({INICIO} a {fim}, {len(unidades())} unidades) | "
           f"estações por unidade: {dict(sorted(defaultdict(int, {u: list(unidade_estacao.values()).count(u) for u in set(unidade_estacao.values())}).items()))}")
    for u in unidades():
        da = [l for l in linhas if l["unidade"] == u]
        avisar(f"  {u:<26} dias com evento {sum(l['evento'] for l in da):>4} | sem chuva "
               f"{100 * sum(l['chuva_dia_mm'] is None for l in da) / len(da):5.1f}% | sem solo "
               f"{100 * sum(l['solo_0_7cm_vespera'] is None for l in da) / len(da):5.1f}%")


if __name__ == "__main__":
    carregar(obter_destino())
