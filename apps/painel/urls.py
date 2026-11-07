from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/situacao.csv", views.situacao_csv, name="situacao_csv"),
    path("calendario/", views.calendario, name="calendario"),
    path("calendario/calendario.csv", views.calendario_csv, name="calendario_csv"),
]
