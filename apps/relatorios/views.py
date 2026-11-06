"""Relatórios."""

from django.shortcuts import redirect, render


def relatorios_view(request):
    return render(request, "relatorios/relatorios.html")
