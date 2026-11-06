from django.urls import path

from . import views

urlpatterns = [
    path("alertas/", views.alertas_view, name="alertas"),
    path("api/alertas/<int:pk>/status/", views.alterar_status_alerta, name="api_alerta_status"),
    path("acoes/", views.acoes_view, name="acoes"),
    path("api/acoes/", views.criar_acao, name="api_criar_acao"),
]
