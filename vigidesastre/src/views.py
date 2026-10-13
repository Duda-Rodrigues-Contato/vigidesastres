from django.http import JsonResponse
import os
#import certifi
#from dotenv import load_dotenv
#from pymongo import MongoClient
from pymongo.server_api import ServerApi
from django.shortcuts import render

#load_dotenv()
#
#
#def mapa_view(request):
#    mongo_uri = os.getenv("MONGO_URI")
#    client = MongoClient(mongo_uri, server_api=ServerApi("1"), tlsCAFile=certifi.where())
#    collection = client["Recife"]["DistritosSanitarios"]
        
#    features = list(collection.find({}, {"_id": 0}))
#    geojson = {"type": "FeatureCollection", "features": features}
        
#    return JsonResponse(geojson)

def mapa_view(request):
    return render(request, 'routes/mapa.html')

def dashboard(request):
    return render(request, 'routes/dashboard.html')
#    return JsonResponse({"message": "Welcome to the Home Dashboard!"})

def alertas_view(request):
    return render(request, 'routes/alertas.html')

def relatorios_view(request):
    return render(request, 'routes/relatorios.html')

def acoes_view(request):
    return render(request, 'routes/acoes.html')