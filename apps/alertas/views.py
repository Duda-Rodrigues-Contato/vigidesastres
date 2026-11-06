"""Alertas e ações de resposta."""

from django.shortcuts import redirect, render


def alertas_view(request):
    return render(request, "alertas/alertas.html")


def acoes_view(request):
    return render(request, "alertas/acoes.html")
