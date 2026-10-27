from django.urls import path

from .views import (
    acoes_view,
    get_arboviroses_bairros_geojson,
    get_arboviroses_resumo,
    get_areas_risco_geojson,
    alertas_view,
    dashboard,
    get_distritos_geojson,
    get_rede_apoio_geojson,
    get_unidades_geojson,
    get_zonas_chuva_geojson,
    index,
    mapa_view,
    relatorios_view,
)

urlpatterns = [
    path("", index, name="index"),
    path("dashboard/", dashboard, name="dashboard"),
    path("mapa/", mapa_view, name="mapa"),
    path("alertas/", alertas_view, name="alertas"),
    path("relatorios/", relatorios_view, name="relatorios"),
    path("acoes/", acoes_view, name="acoes"),
    path("api/distritos/", get_distritos_geojson, name="api_distritos"),
    path("api/unidades/", get_unidades_geojson, name="api_unidades"),
    path("api/zonas-chuva/", get_zonas_chuva_geojson, name="api_zonas_chuva"),
    path("api/areas-risco/", get_areas_risco_geojson, name="api_areas_risco"),
    path("api/arboviroses-bairros/", get_arboviroses_bairros_geojson, name="api_arboviroses_bairros"),
    path("api/arboviroses-resumo/", get_arboviroses_resumo, name="api_arboviroses_resumo"),
    path("api/rede-apoio/", get_rede_apoio_geojson, name="api_rede_apoio"),
]