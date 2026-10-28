"""Chuva, previsão e avisos prontos para o dashboard e o mapa (decisão 006).

  chuva medida  -> CEMADEN (pluviômetros), pela PIOR estação do distrito
  previsão      -> Open-Meteo (modelo), por distrito
  avisos        -> INMET (oficiais)

Sem Django aqui: só monta os dados, para poder ser testado sozinho.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dominio import limiares
from dominio.distritos import nome_distrito

from .repositorios import avisos as repo_avisos
from .repositorios import chuva as repo_chuva
from .repositorios import previsao as repo_previsao

RECIFE = ZoneInfo("America/Recife")
FONTE_CHUVA = "Dados da Rede Observacional do CEMADEN/MCTIC"
HORAS_DESATUALIZADO = 3


def _agora():
    return datetime.now(timezone.utc)


def _utc(dt):
    """Data do pymongo (UTC sem fuso) -> UTC com fuso."""
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def pior_estacao_por_distrito(horas, ate):
    """{distrito_codigo: estação com mais chuva nas `horas` até `ate`}."""
    pior = {}
    for e in repo_chuva.acumulado_por_estacao(horas, ate):  # já vem da mais chuvosa à menos
        pior.setdefault(e.get("distrito_codigo"), e)
    return pior


def resumo_meteo():
    """Os cards do topo: chuva medida 24 h, previsão 24 h e temperatura."""
    ultima = repo_chuva.ultima_leitura()
    previsoes = repo_previsao.por_distrito()
    if not ultima and not previsoes:
        return None

    resumo = {"chuva_24h": None, "chuva_24h_zona": None, "previsao_24h": None, "previsao_24h_zona": None,
              "temp_min": None, "temp_max": None, "coletado_em": ultima,
              "desatualizado": False, "idade_horas": None, "fonte_chuva": FONTE_CHUVA}

    if ultima:
        estacoes = repo_chuva.acumulado_por_estacao(24, ultima)
        if estacoes:
            pior = estacoes[0]
            resumo["chuva_24h"] = pior["chuva_mm"]
            resumo["chuva_24h_zona"] = (f"{nome_distrito(pior.get('distrito_codigo'))} · {pior['nome']}"
                                        if pior["chuva_mm"] > 0 else "em todos os pluviômetros")
        idade = _agora() - ultima
        resumo["idade_horas"] = int(idade.total_seconds() // 3600)
        resumo["desatualizado"] = idade > timedelta(hours=HORAS_DESATUALIZADO)

    com_previsao = [p for p in previsoes if p.get("chuva_prox_24h_mm") is not None]
    if com_previsao:
        pior = max(com_previsao, key=lambda p: p["chuva_prox_24h_mm"])
        resumo["previsao_24h"] = pior["chuva_prox_24h_mm"]
        resumo["previsao_24h_zona"] = pior["distrito"] if pior["chuva_prox_24h_mm"] > 0 else "em todos os distritos"
    temperaturas = [p["temperatura_c"] for p in previsoes if p.get("temperatura_c") is not None]
    if temperaturas:
        resumo["temp_min"], resumo["temp_max"] = min(temperaturas), max(temperaturas)

    resumo["chuva_24h_classe"] = limiares.classificar_chuva(resumo["chuva_24h"])
    resumo["previsao_24h_classe"] = limiares.classificar_chuva(resumo["previsao_24h"])
    if not resumo["coletado_em"] and previsoes:
        resumo["coletado_em"] = _utc(previsoes[0]["coletado_em"])
    return resumo


def chuva_diaria(dias=14):
    """Gráfico dos 14 dias: barras com a média das estações, linha com a pior estação.

    Dia sem nenhuma leitura fica vazio (lacuna), não zero. "hoje" é parcial.
    """
    hoje = _agora().astimezone(RECIFE).date()
    primeiro = hoje - timedelta(days=dias - 1)
    inicio = datetime.combine(primeiro, datetime.min.time(), RECIFE)
    leituras = repo_chuva.leituras_desde(inicio)
    if not leituras:
        return None

    por_estacao_dia = {}
    for l in leituras:
        # a hora fechada é o FIM do intervalo: recua 1 min para o dia certo (00:00 é do dia anterior)
        dia = (_utc(l["hora"]) - timedelta(minutes=1)).astimezone(RECIFE).date()
        chave = (l["codestacao"], dia)
        por_estacao_dia[chave] = por_estacao_dia.get(chave, 0.0) + (l["chuva_mm"] or 0.0)

    datas = [primeiro + timedelta(days=i) for i in range(dias)]
    media, maxima = [], []
    for d in datas:
        valores = [v for (_, dia), v in por_estacao_dia.items() if dia == d]
        media.append(round(sum(valores) / len(valores), 1) if valores else None)
        maxima.append(round(max(valores), 1) if valores else None)
    rotulos = [d.strftime("%d/%m") for d in datas]
    rotulos[-1] = "hoje"
    return {"rotulos": rotulos, "series": [
        {"nome": "Média dos pluviômetros", "valores": media, "tipo": "bar"},
        {"nome": "Pior pluviômetro do dia", "valores": maxima, "tipo": "line"},
    ]}


def distritos_para_gatilhos():
    """Um item por distrito para limiares.avaliar_gatilhos.

    Previsão 24 h: Open-Meteo. Acumulado 72 h: a PIOR estação do distrito (medido).
    """
    previsoes = repo_previsao.por_distrito()
    if not previsoes:
        return []
    ultima = repo_chuva.ultima_leitura()
    pior72 = pior_estacao_por_distrito(72, ultima) if ultima else {}
    return [{
        "nome": p["distrito"],
        "codigo": p["distrito_codigo"],
        "chuva_prox_24h_mm": p.get("chuva_prox_24h_mm"),
        "chuva_72h_mm": pior72[p["distrito_codigo"]]["chuva_mm"] if p["distrito_codigo"] in pior72 else None,
    } for p in previsoes]


def proximas_48h(distritos, mare):
    """Chuva prevista (distrito com maior previsão) e maré, hora a hora."""
    agora = _agora()
    fim = agora + timedelta(hours=48)
    pontos = {}
    com_previsao = [d for d in distritos if d.get("chuva_prox_24h_mm") is not None]
    distrito = max(com_previsao, key=lambda d: d["chuva_prox_24h_mm"]) if com_previsao else None
    if distrito:
        for r in repo_previsao.serie_futura(distrito["codigo"], agora, fim):
            pontos.setdefault(_utc(r["hora"]), {})["chuva"] = r["chuva_mm"]
    if mare:
        for d in mare["_serie"]:
            if d["hora"] <= fim:
                pontos.setdefault(d["hora"], {})["mare"] = d["nivel_m"]
    if not pontos:
        return None
    horas = sorted(pontos)
    return {
        "rotulos": [h.astimezone(RECIFE).strftime("%d/%m %Hh") for h in horas],
        "chuva": [pontos[h].get("chuva") for h in horas],
        "mare": [pontos[h].get("mare") for h in horas],
        "limiar_mare": mare["limiar_alta"] if mare else None,
        "zona": distrito["nome"] if distrito else None,
    }


def avisos_oficiais():
    """Avisos do INMET em vigor ou a começar, com datas no fuso certo para a tela."""
    return [{**a, "inicio": _utc(a.get("inicio")), "fim": _utc(a.get("fim"))}
            for a in repo_avisos.vigentes_e_proximos()]


def chuva_por_distrito_geojson(distritos_features):
    """Distritos coloridos pela pior estação em 24 h, no formato que o mapa já usa."""
    from shapely.geometry import shape

    ultima = repo_chuva.ultima_leitura()
    pior = pior_estacao_por_distrito(24, ultima) if ultima else {}
    contagem = {}
    for e in repo_chuva.estacoes_ativas():
        contagem[e.get("distrito_codigo")] = contagem.get(e.get("distrito_codigo"), 0) + 1
    features = []
    for f in distritos_features:
        codigo = f["properties"].get("cdistscodi")
        nome = nome_distrito(codigo)
        rotulo = shape(f["geometry"]).representative_point()
        e = pior.get(codigo)
        features.append({"type": "Feature", "geometry": f["geometry"], "properties": {
            "nome": nome, "distritos": [{"nome": nome}],
            "chuva_24h_mm": e["chuva_mm"] if e else None,
            "estacao": e["nome"] if e else None,
            "estacoes": contagem.get(codigo, 0),
            "ponto_rotulo": [round(rotulo.x, 5), round(rotulo.y, 5)],
        }})
    return {"type": "FeatureCollection", "fonte": FONTE_CHUVA,
            "ultima_leitura": ultima.isoformat() if ultima else None, "features": features}


def estacoes_geojson():
    """Pluviômetros ativos como pontos, com a chuva das últimas 24 h."""
    ultima = repo_chuva.ultima_leitura()
    chuva = {e["codestacao"]: e["chuva_mm"] for e in repo_chuva.acumulado_por_estacao(24, ultima)} if ultima else {}
    features = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [e["longitude"], e["latitude"]]},
        "properties": {"codigo": e["codestacao"], "nome": e["nome"],
                       "distrito": nome_distrito(e.get("distrito_codigo")),
                       "chuva_24h_mm": chuva.get(e["codestacao"])},
    } for e in repo_chuva.estacoes_ativas() if e.get("latitude") is not None]
    return {"type": "FeatureCollection", "fonte": FONTE_CHUVA, "features": features}
