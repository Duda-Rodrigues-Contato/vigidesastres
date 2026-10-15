import os

import certifi
from django.http import JsonResponse
from django.shortcuts import redirect, render
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()

BANCO = "Recife"

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
        )
    return _client


# ─── Páginas ──────────────────────────────────────────────────────────


def index(request):
    # A raiz leva direto ao painel: o index.html original é uma folha de
    # exemplos de telas de erro, não uma landing page.
    return redirect("dashboard")


def dashboard(request):
    return render(request, "routes/dashboard.html")


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