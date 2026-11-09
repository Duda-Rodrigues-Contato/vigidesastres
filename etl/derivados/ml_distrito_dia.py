"""Tabela do modelo de risco: uma linha por distrito e dia, 2014-2024 (etapa 3e).

Junta tudo o que foi carregado na etapa 3:
  chuva   CEMADEN por pluviômetro (pior estação do distrito); se o distrito não
          tem estação válida no dia, a estação do INMET (A301) como chuva da cidade
  maré    maré astronômica calculada (máxima e amplitude do dia)
  alvo    atendimentos da Defesa Civil LIGADOS À CHUVA no distrito, no dia (decisão 009)
  contexto  mês, dia da semana, feriado, pandemia, vulnerabilidade do distrito

  gold  gold.ml_distrito_dia

Convenção de tempo (decisão 009): a chuva "do dia" é a do próprio dia D. No uso
diário ela vem da PREVISÃO para amanhã; no treino, da chuva medida (previsão
perfeita, o que deixa a avaliação otimista e precisa constar no relatório).
O "dia crítico" (p95 do distrito) NÃO é calculado aqui: depende do período de
treino e é feito no treino, para não vazar informação do teste.

Uso:
    python -m etl.derivados.ml_distrito_dia
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from shapely.geometry import Point

from dominio.bairros import APELIDOS_PLANO
from dominio.distritos import nome_distrito
from dominio.feriados import feriados_recife
from etl.comum.distritos import distrito_de, distritos_poligonos
from etl.comum.texto import normalizar
from etl.destinos import obter_destino
from etl.destinos.base import Carga

INICIO, FIM = date(2014, 1, 1), date(2024, 12, 31)
MIN_LEITURAS = 20       # estação-dia com menos leituras que isso é "sem dado", não "sem chuva"
MIN_HORAS_INMET = 20
PANDEMIA = (date(2020, 3, 18), date(2021, 12, 31))
# separação do alvo por tipo de evento: a maré só pesa no alagamento (planície)
TERMOS_ALAGAMENTO = ("ALAGA", "INUNDA")
TERMOS_DESLIZAMENTO = ("DESLIZ", "BARREIRA")
# nomes da Defesa Civil que não são bairros do IBGE (1% dos atendimentos, ver dias_criticos.py)
APELIDOS_DC = {**{k: v[0] for k, v in APELIDOS_PLANO.items()}, "BAIRRO DO RECIFE": "RECIFE", "POCO DA PANELA": "POCO"}
COLECAO_COORD = "silver_estacoes_historico"


# ── coordenadas das estações (as paradas hoje não têm coordenada no cadastro diário) ──
def ler_coordenada(texto):
    """(lat, lon) da primeira leitura de um CSV do CEMADEN; None se vazio."""
    from etl.comum.cemaden import ler_serie
    for l in ler_serie(texto):
        try:
            return float(l["latitude"].replace(",", ".")), float(l["longitude"].replace(",", "."))
        except (KeyError, ValueError, AttributeError):
            continue
    return None


def garantir_coordenadas(banco, cliente=None, poligonos=None, avisar=print):
    """{codestacao: distrito}. Busca na API só as estações ainda sem coordenada guardada."""
    from etl.historico.cemaden import UF, janela_do_mes
    conhecidas = {e["codestacao"]: e for e in banco[COLECAO_COORD].find()}
    meses_com_dado = {}
    for c in banco["controle_historico"].find({"fonte": "cemaden", "status": "ok", "dias": {"$gt": 0}}):
        meses_com_dado.setdefault(c["codestacao"], c["mes"])
    faltando = [e for e in meses_com_dado if e not in conhecidas]
    if faltando:
        from etl.comum.cemaden import ClienteCemaden
        cliente = cliente or ClienteCemaden()
        poligonos = poligonos or distritos_poligonos()
        avisar(f"  buscando a coordenada de {len(faltando)} estações...")
        for cod in faltando:
            ano, mes = map(int, meses_com_dado[cod].split("-"))
            coord = ler_coordenada(cliente.serie_csv(cod, UF, *janela_do_mes(ano, mes)))
            if coord:
                distrito = distrito_de(Point(coord[1], coord[0]), poligonos)
                banco[COLECAO_COORD].update_one({"codestacao": cod}, {"$set": {
                    "latitude": coord[0], "longitude": coord[1], "distrito_codigo": distrito}}, upsert=True)
                conhecidas[cod] = {"distrito_codigo": distrito}
    return {cod: e["distrito_codigo"] for cod, e in conhecidas.items()}


# ── montagem ─────────────────────────────────────────────────────────
def _soma(serie, dia, dias):
    """Soma de `dias` dias terminando em `dia`; None se faltar algum."""
    valores = [serie.get(dia - timedelta(n)) for n in range(dias)]
    return None if any(v is None for v in valores) else round(sum(valores), 1)


def montar(estacao_dia, distrito_estacao, inmet_dia, mare_dia, alvo_dia, contexto, inicio=INICIO, fim=FIM):
    """Linhas da tabela. Entradas (todas com chaves date):
      estacao_dia      {(codestacao, dia): (chuva_mm, max_hora_mm, leituras)}
      distrito_estacao {codestacao: distrito}
      inmet_dia        {dia: (chuva_mm, max_hora_mm, horas)}
      mare_dia         {dia: (mare_max_m, amplitude_m)}
      alvo_dia         {(distrito, dia): (chuva, reativos, alagamento, deslizamento)}
      contexto         {distrito: {...variáveis fixas do distrito...}}
    """
    # 1. chuva por distrito e dia: a pior estação válida; senão o INMET
    pior, pico = {}, {}
    for (cod, dia), valores in estacao_dia.items():
        mm, max_h, leituras = valores[:3]
        hora_pico = valores[3] if len(valores) > 3 else None
        distrito = distrito_estacao.get(cod)
        if distrito is None or leituras < MIN_LEITURAS:
            continue
        atual = pior.get((distrito, dia))
        if atual is None or mm > atual[0]:
            pior[(distrito, dia)] = (mm, max_h, cod)
        # a hora mais forte do distrito: a da estação com a maior chuva numa hora
        if hora_pico is not None and max_h > 0 and max_h > pico.get((distrito, dia), (0, None))[0]:
            pico[(distrito, dia)] = (max_h, hora_pico)

    feriados = {}
    for ano in range(inicio.year, fim.year + 1):
        feriados.update(feriados_recife(ano))

    linhas = []
    for distrito in range(1, 9):
        chuva, max_hora, origem = {}, {}, {}
        d = inicio - timedelta(days=7)
        while d <= fim:
            if (distrito, d) in pior:
                chuva[d], max_hora[d], origem[d] = pior[(distrito, d)][0], pior[(distrito, d)][1], "cemaden"
            elif d in inmet_dia and inmet_dia[d][2] >= MIN_HORAS_INMET:
                chuva[d], max_hora[d], origem[d] = inmet_dia[d][0], inmet_dia[d][1], "inmet"
            d += timedelta(1)
        d = inicio
        while d <= fim:
            alvo, reativos, alagamento, deslizamento = (tuple(alvo_dia.get((distrito, d), ())) + (0, 0, 0, 0))[:4]
            mare = mare_dia.get(d, (None, None))
            linhas.append({
                "distrito_codigo": distrito, "distrito": nome_distrito(distrito),
                "data": datetime(d.year, d.month, d.day), "ano": d.year, "mes": d.month,
                "dia_semana": d.weekday(), "fim_de_semana": d.weekday() >= 5,
                "feriado": d in feriados, "pandemia": PANDEMIA[0] <= d <= PANDEMIA[1],
                "chuva_dia_mm": chuva.get(d), "chuva_vespera_mm": chuva.get(d - timedelta(1)),
                "chuva_3d_mm": _soma(chuva, d, 3), "chuva_7d_mm": _soma(chuva, d, 7),
                "max_hora_mm": max_hora.get(d), "fonte_chuva": origem.get(d),
                "chuva_pico_mm": pico.get((distrito, d), (None, None))[0],
                "hora_pico_utc": pico.get((distrito, d), (None, None))[1],
                "mare_max_m": mare[0], "mare_amplitude_m": mare[1],
                **contexto.get(distrito, {}),
                "atendimentos_chuva": alvo, "atendimentos_reativos": reativos,
                "atendimentos_alagamento": alagamento, "atendimentos_deslizamento": deslizamento,
            })
            d += timedelta(1)
    return linhas


def contexto_dos_distritos(banco):
    """Variáveis fixas de cada distrito: população, comunidades e áreas de risco."""
    distrito_do_bairro, pop = {}, defaultdict(int)
    for b in banco["silver_bairros"].find({}, {"chave": 1, "distrito_codigo": 1, "populacao": 1}):
        distrito_do_bairro[b["chave"]] = b.get("distrito_codigo")
        pop[b.get("distrito_codigo")] += b.get("populacao") or 0
    comunidades, alag, desliz = defaultdict(int), defaultdict(int), defaultdict(int)
    for c in banco["silver_comunidades"].find({}, {"chave_bairro": 1}):
        comunidades[distrito_do_bairro.get(c.get("chave_bairro"))] += 1
    for a in banco["silver_areas_risco"].find({}, {"chave": 1, "alagamento": 1, "deslizamento": 1}):
        distrito = distrito_do_bairro.get(a.get("chave"))
        alag[distrito] += len(a.get("alagamento") or [])
        desliz[distrito] += len(a.get("deslizamento") or [])
    return {d: {"populacao": pop[d], "comunidades": comunidades[d], "areas_risco_alagamento": alag[d],
                "areas_risco_deslizamento": desliz[d]} for d in range(1, 9)}


def ler_entradas(banco, distrito_estacao):
    estacao_dia = {(e["codestacao"], e["data"].date()): (e["chuva_mm"], e["max_hora_mm"], e["leituras"],
                                                          e.get("hora_pico_utc"))
                   for e in banco["silver_chuva_estacao_dia"].find()}
    inmet_dia = {e["data"].date(): (e["chuva_mm"], e["max_hora_mm"], e["horas_com_dado"])
                 for e in banco["silver_chuva_inmet_dia"].find()}
    mare_dia = {m["data"].date(): (m["mare_max_m"], m["amplitude_m"]) for m in banco["silver_mare_calculada_dia"].find()}
    distrito_do_bairro = {b["chave"]: b.get("distrito_codigo") for b in banco["silver_bairros"].find({}, {"chave": 1, "distrito_codigo": 1})}
    alvo = defaultdict(lambda: [0, 0, 0, 0])
    for d in banco["silver_defesa_civil_bairro_dia"].find({}, {"data": 1, "bairro": 1, "chuva": 1, "reativos": 1,
                                                              "por_tipo": 1, "por_ocorrencia": 1}):
        bairro = normalizar(d["bairro"])
        distrito = distrito_do_bairro.get(APELIDOS_DC.get(bairro, bairro))
        if distrito:
            a = alvo[(distrito, d["data"].date())]
            a[0] += d.get("chuva") or 0
            a[1] += d.get("reativos") or 0
            tipos = list((d.get("por_tipo") or {}).items()) + list((d.get("por_ocorrencia") or {}).items())
            a[2] += sum(n for t, n in tipos if any(x in t for x in TERMOS_ALAGAMENTO))
            a[3] += sum(n for t, n in tipos if any(x in t for x in TERMOS_DESLIZAMENTO))
    if not estacao_dia:
        raise ValueError("silver_chuva_estacao_dia vazia: rode antes python -m etl.historico.cemaden")
    if not any(a[0] for a in alvo.values()):
        raise ValueError("a Defesa Civil não tem o campo 'chuva': rode python -m etl defesa_civil com o alvo novo")
    return estacao_dia, inmet_dia, mare_dia, {k: tuple(v) for k, v in alvo.items()}


def carregar(destino, avisar=print):
    banco = destino.banco
    distrito_estacao = garantir_coordenadas(banco, avisar=avisar)
    estacao_dia, inmet_dia, mare_dia, alvo = ler_entradas(banco, distrito_estacao)
    linhas = montar(estacao_dia, distrito_estacao, inmet_dia, mare_dia, alvo, contexto_dos_distritos(banco))
    agora = datetime.now(timezone.utc)
    for l in linhas:
        l["coletado_em"] = agora
    destino.carregar(Carga("gold.ml_distrito_dia", linhas, chaves=("distrito_codigo", "data")))

    avisar(f"{len(linhas)} linhas ({len(linhas) // 8} dias x 8 distritos)")
    por_fonte = defaultdict(int)
    for l in linhas:
        por_fonte[l["fonte_chuva"] or "sem chuva"] += 1
    avisar("chuva do dia por fonte: " + ", ".join(f"{k} {100 * v / len(linhas):.1f}%" for k, v in sorted(por_fonte.items())))
    for ano in range(INICIO.year, FIM.year + 1):
        do_ano = [l for l in linhas if l["ano"] == ano]
        sem = sum(l["chuva_dia_mm"] is None for l in do_ano)
        cem = sum(l["fonte_chuva"] == "cemaden" for l in do_ano)
        avisar(f"  {ano}: CEMADEN {100 * cem / len(do_ano):5.1f}% | sem chuva {100 * sem / len(do_ano):5.1f}% | "
               f"atendimentos ligados à chuva: {sum(l['atendimentos_chuva'] for l in do_ano)}")


if __name__ == "__main__":
    carregar(obter_destino())
