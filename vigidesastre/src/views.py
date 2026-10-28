import logging
import statistics
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from pymongo.errors import PyMongoError

from dominio import limiares
from dominio.mare import preamares

from . import painel_chuva
from .repositorios import arboviroses as repo_arboviroses
from .repositorios import mare as repo_mare
from .repositorios import referencia as repo_referencia
from .repositorios.conexao import BANCO, get_mongo_client

logger = logging.getLogger(__name__)


# ─── Páginas ──────────────────────────────────────────────────────────


def index(request):
    # A raiz leva direto ao painel: o index.html original é uma folha de
    # exemplos de telas de erro, não uma landing page.
    return redirect("dashboard")


def _resumo_mare(banco):
    """Próxima maré cheia e se ela é "alta" pelo critério de limiares.py.

    "Alta" = entre as marés cheias mais altas dos últimos 14 dias (percentil
    sobre os PICOS, ou seja, as marés de sizígia).
    """
    docs = repo_mare.serie()
    if not docs:
        return None
    for d in docs:
        d["hora"] = d["hora"].replace(tzinfo=dt_timezone.utc)

    agora = timezone.now()
    picos = preamares(docs)
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


def get_areas_risco_geojson(request):
    """Bairros que contêm áreas de risco alto ou muito alto (R3/R4).

    Fonte: Plano de Contingência 2024 da Defesa Civil do Recife. O plano
    identifica comunidades DENTRO dos bairros; o bairro na camada indica que
    ele contém essas áreas, não que esteja todo em risco.
    """
    features = [
        {
            "type": "Feature",
            "geometry": a["geometria"],
            "properties": {
                "bairro": a["bairro"],
                "tipos": a["tipos"],
                "alagamento": a["alagamento"],
                "deslizamento": a["deslizamento"],
                "total_areas": a["total_areas"],
                "nivel": a["nivel"],
                "fonte": a["fonte"],
            },
        }
        for a in repo_referencia.areas_risco()
    ]
    return JsonResponse({"type": "FeatureCollection", "features": features})


DOENCAS_ARBO = ("dengue", "chikungunya", "zika")


def get_arboviroses_bairros_geojson(request):
    """Casos prováveis e incidência por bairro, num ano. Histórico: o arquivo
    mais recente da prefeitura é de 2025; a semana atual vem do InfoDengue.

    ?ano=2025 (padrão: o mais recente)  ?doenca=dengue|chikungunya|zika|todas
    """
    banco = get_mongo_client()[BANCO]
    anos = sorted(banco["ArboviroseBairroAnual"].distinct("ano"))
    if not anos:
        return JsonResponse({"type": "FeatureCollection", "features": [], "anos": []})

    try:
        ano = int(request.GET.get("ano", anos[-1]))
    except ValueError:
        return JsonResponse({"erro": "ano inválido"}, status=400)
    doenca = request.GET.get("doenca", "todas")
    doencas = DOENCAS_ARBO if doenca == "todas" else (doenca,)
    if not set(doencas) <= set(DOENCAS_ARBO):
        return JsonResponse({"erro": "doença inválida"}, status=400)

    por_bairro = {}
    for r in banco["ArboviroseBairroAnual"].find(
        {"ano": ano, "doenca": {"$in": list(doencas)}}, {"_id": 0}
    ):
        b = por_bairro.setdefault(r["chave"], {"populacao": r["populacao"], "por_doenca": {}})
        b["por_doenca"][r["doenca"]] = r["provaveis"]

    features = []
    for bairro in banco["Bairros"].find({}, {"_id": 0}):
        dados = por_bairro.get(bairro["chave"])
        if not dados:
            continue
        provaveis = sum(dados["por_doenca"].values())
        populacao = dados["populacao"]
        features.append({
            "type": "Feature",
            "geometry": bairro["geometria"],
            "properties": {
                "bairro": bairro["nome"],
                "populacao": populacao,
                "provaveis": provaveis,
                "por_doenca": dados["por_doenca"],
                "incidencia_10k": round(provaveis / populacao * 10_000, 1) if populacao else None,
            },
        })

    return JsonResponse({
        "type": "FeatureCollection",
        "ano": ano, "anos": anos, "doenca": doenca,
        "fonte": "SINAN, via Portal de Dados Abertos do Recife; população: IBGE, Censo 2022",
        "features": features,
    })


def get_arboviroses_resumo(request):
    """Situação da semana na cidade (InfoDengue), para o painel do mapa."""
    resumo = repo_arboviroses.resumo_semana_cidade()
    return JsonResponse({"resumo": resumo})


INDICADORES_COMUNIDADE = {"alagamento": "IND_ALAGAM", "deslizamento": "DENS_ESCOR", "indice": "Indice_COM"}


def get_comunidades_geojson(request):
    """Comunidades de Interesse Social (levantamento de 2014).

    ?indicador=alagamento|deslizamento|indice. Notas de 0 a 10; maior = pior,
    conferido contra o Plano de Contingência 2024 (analises/comunidades/conferir_escalas.py).
    """
    campo = INDICADORES_COMUNIDADE.get(request.GET.get("indicador", "alagamento"))
    if not campo:
        return JsonResponse({"erro": "indicador inválido"}, status=400)
    features = [
        {
            "type": "Feature",
            "geometry": c["geometria"],
            "properties": {
                "nome": c["nome"], "bairro": c["bairro"],
                "populacao_2014": c.get("populacao_2014"), "precariedade": c.get("precariedade"),
                "valor": c["indicadores"].get(campo), "indicadores": c["indicadores"],
            },
        }
        for c in repo_referencia.comunidades()
    ]
    return JsonResponse({"type": "FeatureCollection", "features": features})


TIPOS_REDE = ("abrigo", "escola", "cras")


def get_rede_apoio_geojson(request):
    """Abrigos, escolas e CRAS como pontos. ?tipo=abrigo|escola|cras (opcional)."""
    tipo = request.GET.get("tipo")
    if tipo and tipo not in TIPOS_REDE:
        return JsonResponse({"erro": "tipo inválido"}, status=400)
    features = [
        {
            "type": "Feature",
            "geometry": p["localizacao"],
            "properties": {
                "tipo": p["tipo"],
                "nome": p["nome"],
                "bairro": p["bairro"],
                "endereco": p["endereco"],
                "detalhe": p.get("detalhe", {}),
                "fonte": p["fonte"],
            },
        }
        for p in repo_referencia.rede_apoio(tipo)
    ]
    return JsonResponse({"type": "FeatureCollection", "features": features})


def dashboard(request):
    contexto = {
        "meteo": None,
        "chuva_diaria": None,
        "total_distritos": None,
        "total_unidades": None,
        "mare": None,
        "arboviroses": None,
        "alertas": None,
        "proximas_48h": None,
        "avisos": [],
        "erro_banco": False,
    }
    # A página inicial nunca pode cair por causa do banco: sem conexão,
    # abre com "--" e um aviso, em vez de erro 500.
    try:
        banco = get_mongo_client()[BANCO]
        contexto["meteo"] = painel_chuva.resumo_meteo()
        contexto["chuva_diaria"] = painel_chuva.chuva_diaria()
        contexto["avisos"] = painel_chuva.avisos_oficiais()
        contexto["arboviroses"] = repo_arboviroses.resumo_semana_cidade()

        mare = _resumo_mare(banco)
        distritos = painel_chuva.distritos_para_gatilhos()
        contexto["mare"] = mare
        # None = sem dado para avaliar; [] = avaliado e nenhum gatilho disparou
        contexto["alertas"] = limiares.avaliar_gatilhos(distritos, mare) if distritos else None
        contexto["alertas_altos"] = sum(
            1 for x in contexto["alertas"] or [] if x["nivel"] == "ALTO"
        )
        contexto["proximas_48h"] = painel_chuva.proximas_48h(distritos, mare)
        contexto["total_distritos"] = repo_referencia.total_distritos()
        contexto["total_unidades"] = repo_referencia.total_unidades()
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
    features = repo_referencia.distritos_features()
    return JsonResponse({"type": "FeatureCollection", "features": features})


def get_unidades_geojson(request):
    """Unidades de saúde como GeoJSON, prontas para o Leaflet.

    Aceita ?tipo=2 (ou repetido) para filtrar por código de tipo CNES.
    Unidades sem coordenada ficam de fora: quebrariam a camada do mapa.
    """
    try:
        tipos = [int(t) for t in request.GET.getlist("tipo")]
    except ValueError:
        return JsonResponse({"erro": "parâmetro 'tipo' deve ser numérico"}, status=400)

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
        for u in repo_referencia.unidades_saude(tipos)
    ]

    return JsonResponse({"type": "FeatureCollection", "features": features})


def get_chuva_distritos_geojson(request):
    """Distritos coloridos pela chuva medida em 24 h (pior pluviômetro do distrito)."""
    return JsonResponse(painel_chuva.chuva_por_distrito_geojson(repo_referencia.distritos_features()))


def get_estacoes_chuva_geojson(request):
    """Pluviômetros do CEMADEN como pontos, com a chuva das últimas 24 h."""
    return JsonResponse(painel_chuva.estacoes_geojson())
