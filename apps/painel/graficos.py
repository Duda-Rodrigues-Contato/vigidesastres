"""Dados dos gráficos do dashboard (dados atualizados) e dos de demanda (tela do Calendário).

As funções `montar_*` recebem dados já lidos (fáceis de testar) e devolvem o formato que o
Chart.js usa. `todos()` lê o banco e monta cada gráfico à parte: se um falhar, ele some e os
outros continuam.
"""

import logging
from datetime import date, datetime, timedelta, timezone

from dominio import limiares
from dominio.distritos import ROMANOS

logger = logging.getLogger(__name__)

JANELA_NORMAL_DIAS = 3      # a normal de um dia usa ±3 dias, para não oscilar demais
ANOS_HISTORICO = (2014, 2024)
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


# 2. Chuva prevista para as próximas 24 h, por distrito -------------------------------------
COR_CLASSE = {"Seco": "#cbd5e1", "Chuva muito fraca": "#bfdbfe", "Chuva fraca": "#93c5fd",
              "Chuva moderada": "#3b82f6", "Chuva forte": "#f97316", "Chuva muito forte": "#dc2626"}


def chuva_prevista_distritos(previsoes):
    """Uma barra por distrito, colorida pela classe de chuva (dominio/limiares.py)."""
    docs = sorted((p for p in previsoes or [] if p.get("chuva_prox_24h_mm") is not None),
                  key=lambda p: p["distrito_codigo"])
    if not docs:
        return None
    classes = [limiares.classificar_chuva(p["chuva_prox_24h_mm"]) for p in docs]
    return {"distritos": [p["distrito"] for p in docs], "mm": [p["chuva_prox_24h_mm"] for p in docs],
            "classes": classes, "cores": [COR_CLASSE[c] for c in classes]}


# 3. Chuva dos últimos 30 dias x normal histórica ---------------------------------------------
def normal_por_dia_do_ano(chuva_diaria_historica):
    """{(mes, dia): média da pior chuva do dia na cidade}, com janela de ±3 dias."""
    por_dia = {}
    for data, mm in chuva_diaria_historica:
        if mm is not None:
            por_dia.setdefault((data.month, data.day), []).append(mm)
    normal = {}
    base = date(2001, 1, 1)  # ano não bissexto: 29/02 usa a janela dos vizinhos
    for i in range(365):
        d = base + timedelta(days=i)
        valores = []
        for k in range(-JANELA_NORMAL_DIAS, JANELA_NORMAL_DIAS + 1):
            v = base + timedelta(days=(i + k) % 365)
            valores += por_dia.get((v.month, v.day), [])
        if valores:
            normal[(d.month, d.day)] = round(sum(valores) / len(valores), 1)
    normal[(2, 29)] = normal.get((2, 28))
    return normal


def chuva_30_dias(recente, normal, hoje):
    """recente = chuva_diaria(30) do painel; normal = normal_por_dia_do_ano(...)."""
    if not recente:
        return None
    datas = [hoje - timedelta(days=29 - i) for i in range(30)]
    pior = next((s["valores"] for s in recente["series"] if s["tipo"] == "line"), [])
    normais = [normal.get((d.month, d.day)) for d in datas]
    validos = [(p, n) for p, n in zip(pior, normais) if p is not None and n is not None]
    total, total_normal = sum(p for p, _ in validos), sum(n for _, n in validos)
    return {"rotulos": recente["rotulos"], "chuva": pior, "normal": normais,
            "total_mm": round(total, 1), "normal_mm": round(total_normal, 1),
            "razao": round(total / total_normal, 2) if total_normal else None}


# 4. Onde estamos no ano: atendimentos ---------------------------------------------------------
def sazonalidade_atendimentos(semanais, previsao_docs, hoje):
    """semanais = [(ano, semana, total da cidade)]; previsão = docs de gold_demanda_previsao."""
    por_semana = {}
    for ano, semana, total in semanais:
        por_semana.setdefault(min(semana, 52), []).append(total)
    if not por_semana:
        return None
    semanas = list(range(1, 53))
    serie = [por_semana.get(s, []) for s in semanas]
    # a semana marcada é a da previsão gravada (pode ser uma demonstração); sem previsão, a de hoje
    referencia = date.fromisoformat(previsao_docs[0]["inicio_semana"][:10]) if previsao_docs else hoje
    atual = min(referencia.isocalendar()[1], 52)
    previsto = round(sum(d["previsto"] for d in previsao_docs)) if previsao_docs else None
    return {"rotulos": [f"S{s}" for s in semanas],
            "media": [round(sum(v) / len(v)) if v else None for v in serie],
            "minimo": [min(v) if v else None for v in serie],
            "maximo": [max(v) if v else None for v in serie],
            "semana_atual": atual, "previsto": previsto,
            "completa": all(d.get("completa") for d in previsao_docs) if previsao_docs else False}


# 5. Arboviroses: este ano x ano anterior ------------------------------------------------------
def arboviroses_ano_a_ano(semanas_docs):
    if not semanas_docs:
        return None
    ano = max(d["ano"] for d in semanas_docs)
    serie = {(d["ano"], d["semana"]): d for d in semanas_docs}
    rotulos = list(range(1, 54))
    ultimo = max(d["semana"] for d in semanas_docs if d["ano"] == ano)
    return {"rotulos": [f"SE {s}" for s in rotulos], "ano": ano, "ano_anterior": ano - 1,
            "atual": [serie[(ano, s)]["estimados"] if (ano, s) in serie else None for s in rotulos],
            "anterior": [serie[(ano - 1, s)]["estimados"] if (ano - 1, s) in serie else None for s in rotulos],
            "nivel": [serie[(ano, s)].get("nivel") if (ano, s) in serie else None for s in rotulos],
            "ultima_semana": ultimo}


# 7. Alertas dos últimos 30 dias ---------------------------------------------------------------
def alertas_30_dias(alertas, sem_acao, hoje):
    datas = [hoje - timedelta(days=29 - i) for i in range(30)]
    contagem = {}
    for a in alertas:
        dia = a["criado_em"].date() if isinstance(a["criado_em"], datetime) else a["criado_em"]
        contagem[(dia, a["nivel"])] = contagem.get((dia, a["nivel"]), 0) + 1
    return {"rotulos": [d.strftime("%d/%m") for d in datas],
            "alto": [contagem.get((d, "ALTO"), 0) for d in datas],
            "medio": [contagem.get((d, "MÉDIO"), 0) for d in datas],
            "total": sum(contagem.values()), "sem_acao": sem_acao}


def _data_br(iso):
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return iso


# 8. Demanda prevista por distrito x normal ----------------------------------------------------
def demanda_por_distrito(previsao_docs):
    if not previsao_docs:
        return None
    docs = sorted(previsao_docs, key=lambda d: d["distrito_codigo"])
    return {"distritos": [d["distrito"] for d in docs],
            "previsto": [d["previsto"] for d in docs], "normal": [d.get("normal") for d in docs],
            "real": [d.get("real") for d in docs] if any(d.get("real") is not None for d in docs) else None,
            "inicio": _data_br(docs[0]["inicio_semana"]), "fim": _data_br(docs[0]["fim_semana"]),
            "completa": all(d.get("completa") for d in docs)}


# Calor nas próximas 48 h ---------------------------------------------------------------------
def calor_48h(linhas):
    """linhas: [{_id: hora UTC, indice, temperatura}] - o maior valor entre os distritos em cada hora."""
    if not linhas:
        return None
    from dominio import calor
    from zoneinfo import ZoneInfo
    recife = ZoneInfo("America/Recife")
    def local(h):
        return (h if h.tzinfo else h.replace(tzinfo=timezone.utc)).astimezone(recife)
    return {"rotulos": [local(l["_id"]).strftime("%d/%m %Hh") for l in linhas],
            "indice": [l["indice"] for l in linhas], "temperatura": [l["temperatura"] for l in linhas],
            "cautela_extrema": calor.CAUTELA_EXTREMA, "perigo": calor.PERIGO}


# Números do topo ------------------------------------------------------------------------------
def indicadores(meteo, alertas_abertos, sem_acao, arbo, previsoes=()):
    from dominio import calor
    com_calor = [p for p in previsoes if p.get("indice_calor_max_24h_c") is not None]
    pior = max(com_calor, key=lambda p: p["indice_calor_max_24h_c"]) if com_calor else None
    return {"calor_max": pior["indice_calor_max_24h_c"] if pior else None,
            "calor_faixa": calor.faixa(pior["indice_calor_max_24h_c"]) if pior else None,
            "calor_temp": pior.get("temp_max_24h_c") if pior else None,
            "calor_distrito": pior["distrito"] if pior else None,"chuva_24h": meteo.get("chuva_24h") if meteo else None,
            "chuva_24h_zona": meteo.get("chuva_24h_zona") if meteo else None,
            "previsao_24h": meteo.get("previsao_24h") if meteo else None,
            "previsao_24h_zona": meteo.get("previsao_24h_zona") if meteo else None,
            "alertas_abertos": alertas_abertos, "sem_acao": sem_acao,
            "arbo_estimados": arbo.get("estimados") if arbo else None,
            "arbo_nivel": arbo.get("nivel_nome") if arbo else None,
            "arbo_semana": arbo.get("semana") if arbo else None}


# Leitura do banco -----------------------------------------------------------------------------
def _bloco(nome, funcao):
    try:
        return funcao()
    except Exception:  # noqa: BLE001 - o gráfico que falha some; o dashboard continua
        logger.exception("Falha ao montar o gráfico %s do dashboard", nome)
        return None


def _chuva_historica(banco):
    """Pior chuva do dia na cidade (maior entre os distritos), 2014-2024."""
    return [(d["_id"], d["mm"]) for d in banco["gold_ml_distrito_dia"].aggregate([
        {"$match": {"ano": {"$gte": ANOS_HISTORICO[0], "$lte": ANOS_HISTORICO[1]}, "chuva_dia_mm": {"$ne": None}}},
        {"$group": {"_id": "$data", "mm": {"$max": "$chuva_dia_mm"}}}])]


def _atendimentos_semanais(banco):
    return [(d["_id"]["ano"], d["_id"]["semana"], d["total"]) for d in banco["gold_ml_distrito_dia"].aggregate([
        {"$match": {"ano": {"$gte": 2015, "$lte": ANOS_HISTORICO[1]}}},
        {"$group": {"_id": {"ano": {"$isoWeekYear": "$data"}, "semana": {"$isoWeek": "$data"}},
                    "total": {"$sum": "$atendimentos_reativos"}, "dias": {"$sum": 1}}},
        {"$match": {"dias": {"$gte": 7 * len(ROMANOS)}}}])]


def todos():
    """Só os gráficos com dados atualizados: calor, chuva prevista, chuva medida, arboviroses, alertas."""
    from django.db.models import Count

    from apps.alertas.models import Alerta
    from apps.fontes import painel_chuva
    from apps.fontes.repositorios import arboviroses as repo_arbo
    from apps.fontes.repositorios import conexao
    from apps.fontes.repositorios import previsao as repo_previsao

    hoje = date.today()
    agora = datetime.now(timezone.utc)
    banco = _bloco("banco", conexao.banco)
    previsoes = _bloco("previsão", repo_previsao.por_distrito) or []
    abertos = Alerta.objects.exclude(status=Alerta.Status.ENCERRADO)
    sem_acao = _bloco("sem ação", lambda: abertos.annotate(n=Count("acoes")).filter(n=0).count())
    return {
        "indicadores": _bloco("indicadores", lambda: indicadores(
            painel_chuva.resumo_meteo(), abertos.count(), sem_acao, repo_arbo.resumo_semana_cidade(), previsoes)),
        "calor": _bloco("calor", lambda: calor_48h(repo_previsao.calor_futuro(agora, agora + timedelta(hours=48)))),
        "chuva_prevista": _bloco("chuva prevista", lambda: chuva_prevista_distritos(previsoes)),
        "chuva_30": _bloco("chuva 30 dias", lambda: chuva_30_dias(
            painel_chuva.chuva_diaria(30), normal_por_dia_do_ano(_chuva_historica(banco)), hoje)),
        "arbo": _bloco("arboviroses", lambda: arboviroses_ano_a_ano(repo_arbo.semanas_dois_anos())),
        "alertas": _bloco("alertas", lambda: alertas_30_dias(
            Alerta.objects.filter(criado_em__gte=agora - timedelta(days=30)).values("nivel", "criado_em"),
            sem_acao or 0, hoje)),
    }


def demanda_calendario():
    """Os dois gráficos de demanda, que ficam na tela do Calendário."""
    from apps.fontes.repositorios import conexao
    from apps.fontes.repositorios import demanda as repo_demanda

    previsao = _bloco("demanda", repo_demanda.previsao) or []
    banco = _bloco("banco", conexao.banco)
    return {"sazonalidade": _bloco("sazonalidade", lambda: sazonalidade_atendimentos(
                _atendimentos_semanais(banco), previsao, date.today())),
            "por_distrito": _bloco("demanda por distrito", lambda: demanda_por_distrito(previsao))}
