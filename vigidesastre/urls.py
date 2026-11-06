"""Rotas do Vigidesastres: cada app cuida das suas."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("", include("apps.painel.urls")),
    path("", include("apps.mapa.urls")),
    path("", include("apps.alertas.urls")),
    path("", include("apps.relatorios.urls")),
]
