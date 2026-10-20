import logging
import os
import statistics
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone

import certifi
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from pymongo.server_api import ServerApi

from . import limiares

load_dotenv()

BANCO = "Recife"
logger = logging.getLogger(__name__)

_client = None


def get_mongo_client():
    """Reaproveita uma única conexão em vez de abrir uma por requisição.

    Abrir MongoClient dentro da view criaria uma conexão nova a cada
    acesso, estourando o limite do Atlas no plano gratuito.
    """
    global _client
    if _client is None:
        _client = MongoClient(
            os.getenv("MONGO_URI"),
            server_api=ServerApi("1"),
            tlsCAFile=certifi.where(),
            # padrao e 30 s: com o Atlas fora, a pagina travaria meio minuto
            serverSelectionTimeoutMS=5000,
        )
    return _client


# ─── Páginas ──────────────────────────────────────────────────────────


def index(request):
    # A raiz leva direto ao painel: o index.html original é uma folha de
    # exemplos de telas de erro, não uma landing page.
    return redirect("dashboard")


def _resumo_meteo(banco):
    """Chuva, previsão e temperatura para o card meteorológico.

    A cidade tem várias zonas de chuva; o card mostra a PIOR, nomeada.
    Uma média esconderia justamente a zona que precisa de atenção.
    """
    zonas = list(banco["ZonasChuva"].find({}, {"_id": 0, "geometria": 0}))
    if not zonas:
        return None

    def pior(campo):
        zona = max(zonas, key=lambda z: z.get(campo) or 0)
        valor = zona.get(campo)
        if valor is None:  # zonas gravadas antes da previsão existir
            return None, None
        return valor, (zona["nome"] if valor > 0 else "em todas as zonas")

    chuva_24h, chuva_24h_zona = pior("chuva_24h_mm")
    previsao_24h, previsao_24h_zona = pior("chuva_prox_24h_mm")

    temperaturas = [
        d["temperatura_c"]
        for z in zonas
        for d in z["distritos"]
        if d.get("temperatura_c") is not None
    ]

    # o pymongo devolve datetime sem fuso; o valor gravado é UTC
    coletado_em = zonas[0]["coletado_em"].replace(tzinfo=dt_timezone.utc)
    idade = timezone.now() - coletado_em

    return {
        "chuva_24h": chuva_24h,
        "chuva_24h_zona": chuva_24h_zona,
        "previsao_24h": previsao_24h,
        "previsao_24h_zona": previsao_24h_zona,
        "chuva_24h_classe": limiares.classificar_chuva(chuva_24h),
        "previsao_24h_classe": limiares.classificar_chuva(previsao_24h),
        "temp_min": min(temperaturas) if temperaturas else None,
        "temp_max": max(temperaturas) if temperaturas else None,
        "coletado_em": timezone.localtime(coletado_em),
        "desatualizado": idade > timedelta(hours=3),
        "idade_horas": int(idade.total_seconds() // 3600),
    }


def _chuva_diaria(banco, dias=14):
    """Chuva diária por zona, para o gráfico do dashboard.

    São ~1.300 registros horários (14 dias x zonas x 24 h): o agrupamento
    por dia é feito aqui no Python, no fuso do Recife.
    """
    zonas = list(banco["ZonasChuva"].find({}, {"_id": 0, "nome": 1, "distritos": 1}))
    if not zonas:
        return None

    # dentro da zona a chuva é idêntica: um distrito de referência basta
    referencia = {z["distritos"][0]["codigo"]: z["nome"] for z in zonas}

    hoje = timezone.localdate()
    primeiro_dia = hoje - timedelta(days=dias - 1)
    # meia-noite local do primeiro dia, convertida para UTC sem fuso,
    # que é como o pymongo grava e compara datas
    inicio = (
        timezone.make_aware(datetime.combine(primeiro_dia, time.min))
        .astimezone(dt_timezone.utc)
        .replace(tzinfo=None)
    )

    registros = banco["MeteoHorario"].find(
        {
            "distrito_codigo": {"$in": list(referencia)},
            "previsao": False,
            "hora": {"$gt": inicio},
        },
        {"_id": 0, "distrito_codigo": 1, "hora": 1, "chuva_mm": 1},
    )

    soma = {}
    for r in registros:
        # cada valor horário é a chuva da hora ANTERIOR: recua 1 h antes de
        # decidir o dia, senão a chuva das 23h-0h cairia no dia seguinte
        hora = r["hora"].replace(tzinfo=dt_timezone.utc) - timedelta(hours=1)
        chave = (r["distrito_codigo"], timezone.localtime(hora).date())
        soma[chave] = soma.get(chave, 0.0) + (r["chuva_mm"] or 0.0)

    datas = [primeiro_dia + timedelta(days=i) for i in range(dias)]
    rotulos = [d.strftime("%d/%m") for d in datas]
    rotulos[-1] = "hoje"

    series = [
        {
            "nome": nome,
            # dia sem coleta fica vazio (lacuna no gráfico), não zero
            "valores": [
                round(soma[(codigo, d)], 1) if (codigo, d) in soma else None
                for d in datas
            ],
        }
        for codigo, nome in sorted(referencia.items())
    ]
    return {"rotulos": rotulos, "series": series}


def _preamares(serie):
    """Marés cheias: picos locais da série horária."""
    return [
        atual
        for anterior, atual, seguinte in zip(serie, serie[1:], serie[2:])
        if atual["nivel_m"] > anterior["nivel_m"] and atual["nivel_m"] >= seguinte["nivel_m"]
    ]


def _resumo_mare(banco):
    """Próxima maré cheia e se ela é "alta" pelo critério de limiares.py.

    "Alta" = entre as marés cheias mais altas dos últimos 14 dias (percentil
    sobre os PICOS, ou seja, as marés de sizígia).
    """
    docs = list(
        banco["MareHorario"]
        .find({"nivel_m": {"$ne": None}}, {"_id": 0, "hora": 1, "nivel_m": 1, "previsao": 1, "coletado_em": 1})
        .sort("hora", 1)
    )
    if not docs:
        return None
    for d in docs:
        d["hora"] = d["hora"].replace(tzinfo=dt_timezone.utc)

    agora = timezone.now()
    picos = _preamares(docs)
    corte = agora - timedelta(days=14)
    picos_14d = [p["nivel_m"] for p in picos if not p["previsao"] and p["hora"] > corte]
    futuros = [p for p in picos if p["previsao"] and p["hora"] > agora]
    if len(picos_14d) < 5 or not futuros:
        return None  # pouco histórico para o critério relativo, ou sem previsão

    limiar = statistics.quantiles(picos_14d, n=100, method="inclusive")[
        limiares.PERCENTIL_MARE_ALTA - 1
    ]
    janela_24h = [p for p in futuros if p["hora"] <= agora + timedelta(hours=24)] or futuros[:1]
    maior = max(janela_24h, key=lambda p: p["nivel_m"])
    proxima = futuros[0]
    coletado_em = docs[0]["coletado_em"].replace(tzinfo=dt_timezone.utc)

    def quando(p):
        return timezone.localtime(p["hora"]).strftime("%d/%m às %H:%M")

    return {
        "proxima_nivel": proxima["nivel_m"],
        "proxima_quando": quando(proxima),
        "proxima_alta": proxima["nivel_m"] >= limiar,
        "nivel_m": maior["nivel_m"],
        "quando": quando(maior),
        "alta_prevista": maior["nivel_m"] >= limiar,
        "limiar_alta": round(limiar, 2),
        "desatualizado": agora - coletado_em > timedelta(hours=6),
        "_serie": [d for d in docs if d["hora"] > agora],
    }


def _zonas_para_gatilhos(banco):
    """Zonas com previsão 24 h e chuva acumulada nas últimas 72 h."""
    zonas = list(banco["ZonasChuva"].find({}, {"_id": 0, "geometria": 0}))
    if not zonas:
        return []
    # dentro da zona a chuva é idêntica: um distrito de referência basta
    referencia = {z["distritos"][0]["codigo"]: z["nome"] for z in zonas}
    coletado = zonas[0]["coletado_em"]  # sem fuso, em UTC, como o pymongo grava
    inicio = coletado - timedelta(hours=limiares.JANELA_ACUMULADO_H)

    acumulado = {}
    for r in banco["MeteoHorario"].find(
        {
            "distrito_codigo": {"$in": list(referencia)},
            "previsao": False,
            "hora": {"$gt": inicio, "$lte": coletado},
        },
        {"_id": 0, "distrito_codigo": 1, "chuva_mm": 1},
    ):
        nome = referencia[r["distrito_codigo"]]
        acumulado[nome] = acumulado.get(nome, 0.0) + (r["chuva_mm"] or 0.0)

    return [
        {
            "nome": z["nome"],
            "codigo_referencia": z["distritos"][0]["codigo"],
            "chuva_prox_24h_mm": z.get("chuva_prox_24h_mm"),
            "chuva_72h_mm": round(acumulado.get(z["nome"], 0.0), 1),
        }
        for z in zonas
    ]


def _proximas_48h(banco, zonas, mare):
    """Chuva prevista (pior zona) e maré, hora a hora, para o gráfico."""
    agora = timezone.now()
    fim = agora + timedelta(hours=48)
    pontos = {}

    com_previsao = [z for z in zonas if z.get("chuva_prox_24h_mm") is not None]
    zona = max(com_previsao, key=lambda z: z["chuva_prox_24h_mm"]) if com_previsao else None
    if zona:
        for r in banco["MeteoHorario"].find(
            {
                "distrito_codigo": zona["codigo_referencia"],
                "previsao": True,
                "hora": {
                    "$gt": agora.astimezone(dt_timezone.utc).replace(tzinfo=None),
                    "$lte": fim.astimezone(dt_timezone.utc).replace(tzinfo=None),
                },
            },
            {"_id": 0, "hora": 1, "chuva_mm": 1},
        ):
            hora = r["hora"].replace(tzinfo=dt_timezone.utc)
            pontos.setdefault(hora, {})["chuva"] = r["chuva_mm"]

    if mare:
        for d in mare["_serie"]:
            if d["hora"] <= fim:
                pontos.setdefault(d["hora"], {})["mare"] = d["nivel_m"]

    if not pontos:
        return None
    horas = sorted(pontos)
    return {
        "rotulos": [timezone.localtime(h).strftime("%d/%m %Hh") for h in horas],
        "chuva": [pontos[h].get("chuva") for h in horas],
        "mare": [pontos[h].get("mare") for h in horas],
        "limiar_mare": mare["limiar_alta"] if mare else None,
        "zona": zona["nome"] if zona else None,
    }


def dashboard(request):
    contexto = {
        "meteo": None,
        "chuva_diaria": None,
        "total_distritos": None,
        "total_unidades": None,
        "mare": None,
        "alertas": None,
        "proximas_48h": None,
        "erro_banco": False,
    }
    # A página inicial nunca pode cair por causa do banco: sem conexão,
    # abre com "--" e um aviso, em vez de erro 500.
    try:
        banco = get_mongo_client()[BANCO]
        contexto["meteo"] = _resumo_meteo(banco)
        contexto["chuva_diaria"] = _chuva_diaria(banco)

        mare = _resumo_mare(banco)
        zonas = _zonas_para_gatilhos(banco)
        contexto["mare"] = mare
        # None = sem dado para avaliar; [] = avaliado e nenhum gatilho disparou
        contexto["alertas"] = limiares.avaliar_gatilhos(zonas, mare) if zonas else None
        contexto["alertas_altos"] = sum(
            1 for x in contexto["alertas"] or [] if x["nivel"] == "ALTO"
        )
        contexto["proximas_48h"] = _proximas_48h(banco, zonas, mare)
        contexto["total_distritos"] = banco["DistritosSanitarios"].count_documents({})
        # mesmo critério do mapa: só unidades com coordenada
        contexto["total_unidades"] = banco["UnidadesSaude"].count_documents(
            {"localizacao": {"$ne": None}}
        )
    except PyMongoError:
        logger.exception("Falha ao consultar o MongoDB para o dashboard")
        contexto["erro_banco"] = True

    return render(request, "routes/dashboard.html", contexto)


def mapa_view(request):
    return render(request, "routes/mapa.html")


def alertas_view(request):
    return render(request, "routes/alertas.html")


def relatorios_view(request):
    return render(request, "routes/relatorios.html")


def acoes_view(request):
    return render(request, "routes/acoes.html")


# ─── API ──────────────────────────────────────────────────────────────


def get_distritos_geojson(request):
    """Distritos sanitários do Recife (8, desde a reorganização de 2014).

    O GeoJSON do portal da prefeitura traz apenas o campo numérico
    `cdistscodi` (1 a 8); a conversão para "DS I"..."DS VIII" é feita
    no front-end.
    """
    colecao = get_mongo_client()[BANCO]["DistritosSanitarios"]
    features = list(colecao.find({}, {"_id": 0}))
    return JsonResponse({"type": "FeatureCollection", "features": features})


def get_unidades_geojson(request):
    """Unidades de saúde como GeoJSON, prontas para o Leaflet.

    Aceita ?tipo=2 (ou repetido) para filtrar por código de tipo CNES.
    Unidades sem coordenada ficam de fora: quebrariam a camada do mapa.
    """
    colecao = get_mongo_client()[BANCO]["UnidadesSaude"]

    filtro = {"localizacao": {"$ne": None}}

    tipos = request.GET.getlist("tipo")
    if tipos:
        try:
            filtro["codigo_tipo"] = {"$in": [int(t) for t in tipos]}
        except ValueError:
            return JsonResponse(
                {"erro": "parâmetro 'tipo' deve ser numérico"}, status=400
            )

    projecao = {
        "_id": 0,
        "localizacao": 1,
        "nome": 1,
        "tipo": 1,
        "codigo_tipo": 1,
        "bairro": 1,
        "turno": 1,
    }

    features = [
        {
            "type": "Feature",
            "geometry": u["localizacao"],
            "properties": {
                "nome": u.get("nome"),
                "tipo": u.get("tipo"),
                "codigo_tipo": u.get("codigo_tipo"),
                "bairro": u.get("bairro"),
                "turno": u.get("turno"),
            },
        }
        for u in colecao.find(filtro, projecao)
    ]

    return JsonResponse({"type": "FeatureCollection", "features": features})


def get_zonas_chuva_geojson(request):
    """Zonas de chuva estimada: distritos fundidos por célula do modelo.

    O Open-Meteo enxerga o Recife em poucas células, então vários
    distritos recebem a mesma chuva. Mostrar a zona inteira é mais
    honesto do que repetir o mesmo número em cada distrito.
    """
    colecao = get_mongo_client()[BANCO]["ZonasChuva"]

    features = []
    coletado_em = None
    for z in colecao.find({}, {"_id": 0}):
        coletado_em = z.get("coletado_em")
        features.append(
            {
                "type": "Feature",
                "geometry": z["geometria"],
                "properties": {
                    "zona_id": z["zona_id"],
                    "nome": z["nome"],
                    "chuva_24h_mm": z["chuva_24h_mm"],
                    "chuva_7d_mm": z["chuva_7d_mm"],
                    "distritos": z["distritos"],
                    "ponto_rotulo": z.get("ponto_rotulo"),
                    "chuva_prox_24h_mm": z.get("chuva_prox_24h_mm"),
                },
            }
        )

    # o pymongo devolve datetime sem fuso; o valor gravado é UTC
    if coletado_em is not None:
        coletado_em = coletado_em.replace(tzinfo=dt_timezone.utc).isoformat()

    return JsonResponse(
        {
            "type": "FeatureCollection",
            "coletado_em": coletado_em,
            "fonte": "Open-Meteo — modelo meteorológico, não medição",
            "features": features,
        }
    )