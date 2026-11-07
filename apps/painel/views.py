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
import csv

from django.http import HttpResponse

from apps.alertas.models import AcaoResposta
from apps.painel.saude import saude_dos_dados
from apps.painel.situacao import resumo_geral, situacao_por_distrito
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
        if contexto["chuva_diaria"]:
            contexto["chuva_diaria"]["limiares"] = [
                {"nome": "Chuva forte", "mm": limiares.CHUVA_FORTE, "cor": "#f97316"},
                {"nome": "Chuva muito forte", "mm": limiares.CHUVA_MUITO_FORTE, "cor": "#dc2626"},
            ]
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
    try:
        contexto["situacao"] = situacao_por_distrito()
        contexto["faixa"] = resumo_geral(contexto["situacao"], contexto.get("avisos") or [])
        contexto["saude"] = saude_dos_dados()
    except Exception:  # noqa: BLE001 - a faixa some, o resto do dashboard continua
        logger.exception("Falha ao montar a situação dos distritos")
    try:
        em_andamento = AcaoResposta.objects.filter(status=AcaoResposta.Status.ANDAMENTO)
        contexto["acoes_andamento"] = em_andamento.count()
        contexto["equipes_mobilizadas"] = em_andamento.values("equipe").distinct().count()
    except Exception:  # noqa: BLE001 - o dashboard nunca cai por causa do PostgreSQL
        logger.exception("Falha ao consultar o PostgreSQL para o dashboard")

    return render(request, "painel/dashboard.html", contexto)


def situacao_csv(request):
    """A matriz dos distritos como planilha (requisito: exportar para planilha)."""
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = 'attachment; filename="situacao_distritos.csv"'
    resposta.write("\ufeff")  # BOM: o Excel abre os acentos certos
    w = csv.writer(resposta, delimiter=";")
    w.writerow(["Distrito", "Situação", "Chuva 24h (mm)", "Pluviômetro", "Chuva 72h (mm)",
                "Previsão 24h (mm)", "Alertas abertos", "Motivos"])
    for d in situacao_por_distrito():
        w.writerow([d["nome"], d["nivel"], d["chuva_24h_mm"], d["estacao_24h"], d["chuva_72h_mm"],
                    d["previsao_24h_mm"], d["alertas_abertos"], " | ".join(d["motivos"])])
    return resposta


MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _tom(indice):
    """Cor da célula pelo índice (mês ÷ média do próprio distrito)."""
    if indice >= 2:
        return "muito_alto"
    if indice >= 1.5:
        return "alto"
    if indice >= 1:
        return "acima"
    return "abaixo" if indice >= 0.6 else "baixo"


def calendario(request):
    """Calendário de risco: em que meses cada distrito mais precisa de equipe."""
    from apps.fontes.repositorios import calendario as repo_calendario
    linhas, erro = [], False
    try:
        meses, resumos = repo_calendario.por_mes(), {r["distrito_codigo"]: r for r in repo_calendario.por_distrito()}
        por_distrito = {}
        for m in meses:
            por_distrito.setdefault(m["distrito_codigo"], []).append({
                **m, "tom": _tom(m["indice"]), "rotulo": MESES_CURTOS[m["mes"] - 1],
                "dica": (f"{m['media_dia']} atendimentos/dia em média ({m['indice']}x a média do distrito). "
                         f"Ano mais calmo: {m['ano_calmo']} ({m['media_ano_calmo']}/dia); "
                         f"mais intenso: {m['ano_intenso']} ({m['media_ano_intenso']}/dia).")})
        for codigo, celulas in sorted(por_distrito.items()):
            linhas.append({"nome": celulas[0]["distrito"], "celulas": celulas, "resumo": resumos.get(codigo, {})})
    except PyMongoError:
        logger.exception("Falha ao ler o calendário de risco")
        erro = True
    return render(request, "painel/calendario.html", {"linhas": linhas, "meses": MESES_CURTOS, "erro": erro})


def calendario_csv(request):
    from apps.fontes.repositorios import calendario as repo_calendario
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = 'attachment; filename="calendario_risco.csv"'
    resposta.write("\ufeff")
    w = csv.writer(resposta, delimiter=";")
    w.writerow(["Distrito", "Mês", "Atendimentos reativos por dia (média 2014-2024)", "Índice (mês / média do distrito)",
                "Ano mais calmo", "Média no ano mais calmo", "Ano mais intenso", "Média no ano mais intenso"])
    for m in repo_calendario.por_mes():
        w.writerow([m["distrito"], m["mes"], m["media_dia"], m["indice"], m["ano_calmo"], m["media_ano_calmo"],
                    m["ano_intenso"], m["media_ano_intenso"]])
    return resposta

