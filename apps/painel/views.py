"""Dashboard: situação do dia."""

import logging
import statistics
from datetime import timedelta
from datetime import timezone as dt_timezone
from django.shortcuts import redirect, render
from django.utils import timezone
from pymongo.errors import PyMongoError
from dominio import limiares
from dominio.mare import preamares
from apps.fontes import painel_chuva
from apps.fontes.resumo_mare import resumo_mare
from apps.fontes.repositorios import arboviroses as repo_arboviroses
from apps.fontes.repositorios import mare as repo_mare
from apps.fontes.repositorios import referencia as repo_referencia
from apps.fontes.repositorios.conexao import BANCO, get_mongo_client

logger = logging.getLogger(__name__)


def dashboard(request):
    contexto = {
        "meteo": None,
        "chuva_diaria": None,
        "total_distritos": None,
        "total_unidades": None,
        "mare": None,
        "arboviroses": None,
        "alertas": None,
        "proximas_48h": None,
        "avisos": [],
        "erro_banco": False,
    }
    # A página inicial nunca pode cair por causa do banco: sem conexão,
    # abre com "--" e um aviso, em vez de erro 500.
    try:
        banco = get_mongo_client()[BANCO]
        contexto["meteo"] = painel_chuva.resumo_meteo()
        contexto["chuva_diaria"] = painel_chuva.chuva_diaria()
        contexto["avisos"] = painel_chuva.avisos_oficiais()
        contexto["arboviroses"] = repo_arboviroses.resumo_semana_cidade()

        mare = resumo_mare()
        distritos = painel_chuva.distritos_para_gatilhos()
        contexto["mare"] = mare
        # None = sem dado para avaliar; [] = avaliado e nenhum gatilho disparou
        contexto["alertas"] = limiares.avaliar_gatilhos(distritos, mare) if distritos else None
        contexto["alertas_altos"] = sum(
            1 for x in contexto["alertas"] or [] if x["nivel"] == "ALTO"
        )
        contexto["proximas_48h"] = painel_chuva.proximas_48h(distritos, mare)
        contexto["total_distritos"] = repo_referencia.total_distritos()
        contexto["total_unidades"] = repo_referencia.total_unidades()
    except PyMongoError:
        logger.exception("Falha ao consultar o MongoDB para o dashboard")
        contexto["erro_banco"] = True

    return render(request, "painel/dashboard.html", contexto)
