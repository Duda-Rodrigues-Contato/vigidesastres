from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/situacao.csv", views.situacao_csv, name="situacao_csv"),
]
