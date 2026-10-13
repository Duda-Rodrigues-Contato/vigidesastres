from django.urls import path
from .views import dashboard, mapa_view, alertas_view, relatorios_view, acoes_view

urlpatterns = [
    # path('api/distritos/', get_distritos_geojson, name='api_distritos'),
    path('dashboard/', dashboard, name='dashboard'),
    path('mapa/', mapa_view, name='mapa'),
    path('alertas/', alertas_view, name='alertas'),
    path('relatorios/', relatorios_view, name='relatorios'),
    path('acoes/', acoes_view, name='acoes'),
]