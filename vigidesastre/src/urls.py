from django.urls import path

from .views import (
    acoes_view,
    alertas_view,
    dashboard,
    get_distritos_geojson,
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
]