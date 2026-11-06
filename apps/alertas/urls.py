from django.urls import path

from . import views

urlpatterns = [
    path("alertas/", views.alertas_view, name="alertas"),
    path("acoes/", views.acoes_view, name="acoes"),
]
