import os

import certifi
from django.http import JsonResponse
from django.shortcuts import redirect, render
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()

_client = None


def get_mongo_client():
    """Reaproveita uma única conexão em vez de abrir uma por requisição."""
    global _client
    if _client is None:
        _client = MongoClient(
            os.getenv("MONGO_URI"),
            server_api=ServerApi("1"),
            tlsCAFile=certifi.where(),
        )
    return _client


def index(request):
    return redirect("dashboard")


def _index_antigo(request):
    return render(request, "routes/index.html")


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


def get_distritos_geojson(request):
    collection = get_mongo_client()["Recife"]["DistritosSanitarios"]
    features = list(collection.find({}, {"_id": 0}))
    return JsonResponse({"type": "FeatureCollection", "features": features})
