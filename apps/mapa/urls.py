from django.urls import path

from . import views

urlpatterns = [
    path("mapa/", views.mapa_view, name="mapa"),
    path("api/distritos/", views.get_distritos_geojson, name="api_distritos"),
    path("api/unidades/", views.get_unidades_geojson, name="api_unidades"),
    path("api/chuva-distritos/", views.get_chuva_distritos_geojson, name="api_chuva_distritos"),
    path("api/estacoes-chuva/", views.get_estacoes_chuva_geojson, name="api_estacoes_chuva"),
    path("api/areas-risco/", views.get_areas_risco_geojson, name="api_areas_risco"),
    path("api/arboviroses-bairros/", views.get_arboviroses_bairros_geojson, name="api_arboviroses_bairros"),
    path("api/arboviroses-resumo/", views.get_arboviroses_resumo, name="api_arboviroses_resumo"),
    path("api/comunidades/", views.get_comunidades_geojson, name="api_comunidades"),
    path("api/rede-apoio/", views.get_rede_apoio_geojson, name="api_rede_apoio"),
]
