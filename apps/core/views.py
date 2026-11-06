"""Página inicial."""

from django.shortcuts import redirect, render


def index(request):
    # A raiz leva direto ao painel: o index.html original é uma folha de
    # exemplos de telas de erro, não uma landing page.
    return redirect("dashboard")
