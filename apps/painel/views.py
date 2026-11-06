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
from apps.fontes.repositorios import arboviroses as repo_arboviroses
from apps.fontes.repositorios import mare as repo_mare
from apps.fontes.repositorios import referencia as repo_referencia
from apps.fontes.repositorios.conexao import BANCO, get_mongo_client

logger = logging.getLogger(__name__)


def _resumo_mare(banco):
    """Próxima maré cheia e se ela é "alta" pelo critério de limiares.py.

    "Alta" = entre as marés cheias mais altas dos últimos 14 dias (percentil
    sobre os PICOS, ou seja, as marés de sizígia).
    """
    docs = repo_mare.serie()
    if not docs:
        return None
    for d in docs:
        d["hora"] = d["hora"].replace(tzinfo=dt_timezone.utc)

    agora = timezone.now()
    picos = preamares(docs)
    corte = agora - timedelta(days=14)
    picos_14d = [p["nivel_m"] for p in picos if not p["previsao"] and p["hora"] > corte]
    futuros = [p for p in picos if p["previsao"] and p["hora"] > agora]
    if len(picos_14d) < 5 or not futuros:
        return None  # pouco histórico para o critério relativo, ou sem previsão

    limiar = statistics.quantiles(picos_14d, n=100, method="inclusive")[
        limiares.PERCENTIL_MARE_ALTA - 1
    ]
    janela_24h = [p for p in futuros if p["hora"] <= agora + timedelta(hours=24)] or futuros[:1]
    maior = max(janela_24h, key=lambda p: p["nivel_m"])
    proxima = futuros[0]
    coletado_em = docs[0]["coletado_em"].replace(tzinfo=dt_timezone.utc)

    def quando(p):
        return timezone.localtime(p["hora"]).strftime("%d/%m às %H:%M")

    return {
        "proxima_nivel": proxima["nivel_m"],
        "proxima_quando": quando(proxima),
        "proxima_alta": proxima["nivel_m"] >= limiar,
        "nivel_m": maior["nivel_m"],
        "quando": quando(maior),
        "alta_prevista": maior["nivel_m"] >= limiar,
        "limiar_alta": round(limiar, 2),
        "desatualizado": agora - coletado_em > timedelta(hours=6),
        "_serie": [d for d in docs if d["hora"] > agora],
    }


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

        mare = _resumo_mare(banco)
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
