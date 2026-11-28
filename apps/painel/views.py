"""Dashboard: situação do dia."""

import logging
from django.shortcuts import render
from pymongo.errors import PyMongoError
import csv

from django.http import HttpResponse

from apps.painel.saude import saude_dos_dados
from apps.painel.situacao import situacao_por_distrito

logger = logging.getLogger(__name__)


def dashboard(request):
    """Dashboard em gráficos, só com dados atualizados (dados em apps/painel/graficos.py).

    A página nunca cai por causa do banco: cada gráfico é montado à parte e, sem dado, mostra
    um aviso no lugar."""
    from apps.painel import graficos

    try:
        saude = saude_dos_dados()
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao ler a saúde dos dados")
        saude = None
    contexto = {"saude": saude, **graficos.todos()}
    contexto["erro_banco"] = not any(contexto.get(k) for k in ("calor", "chuva_prevista", "chuva_30", "arbo"))
    return render(request, "painel/dashboard.html", contexto)


def situacao_csv(request):
    """A matriz dos distritos como planilha (requisito: exportar para planilha)."""
    try:
        situacao = situacao_por_distrito()
    except Exception:  # noqa: BLE001 - sem dados, a planilha avisa em vez de dar erro 500
        logger.exception("Falha ao montar a planilha da situação")
        return HttpResponse("Dados indisponíveis no momento.", status=503, content_type="text/plain; charset=utf-8")
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = 'attachment; filename="situacao_distritos.csv"'
    resposta.write("\ufeff")  # BOM: o Excel abre os acentos certos
    w = csv.writer(resposta, delimiter=";")
    w.writerow(["Distrito", "Situação", "Chuva 24h (mm)", "Pluviômetro", "Chuva 72h (mm)",
                "Previsão 24h (mm)", "Alertas abertos", "Motivos"])
    for d in situacao:
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
    linhas, erro, demanda = [], False, None
    try:
        demanda = _demanda_da_semana()
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
    from apps.painel import graficos
    return render(request, "painel/calendario.html",
                  {"linhas": linhas, "meses": MESES_CURTOS, "erro": erro, "demanda": demanda,
                   "graficos_demanda": graficos.demanda_calendario()})


def _demanda_da_semana():
    """Previsão de atendimentos da semana por distrito (ml.demanda), pronta para a tela."""
    from datetime import date
    from apps.fontes.repositorios import demanda as repo_demanda
    docs = repo_demanda.previsao()
    if not docs:
        return None
    for d in docs:
        v = d.get("variacao")
        d["tom"] = ("muito_alto" if v is not None and v >= 0.5 else "alto" if v is not None and v >= 0.2
                    else "abaixo" if v is not None and v <= -0.2 else "normal")
        d["variacao_pct"] = None if v is None else round(100 * v)
    primeiro = docs[0]
    data = lambda iso: date.fromisoformat(iso[:10]).strftime("%d/%m/%Y") if iso else "?"
    return {"distritos": docs, "inicio": data(primeiro["inicio_semana"]), "fim": data(primeiro["fim_semana"]),
            "completa": all(d.get("completa") for d in docs), "dados_ate": data(primeiro.get("dados_ate")),
            "demonstracao": primeiro.get("demonstracao", False)}


def calendario_csv(request):
    from apps.fontes.repositorios import calendario as repo_calendario
    try:
        meses = repo_calendario.por_mes()
    except PyMongoError:
        logger.exception("Falha ao ler o calendário de risco para a planilha")
        return HttpResponse("Dados indisponíveis no momento.", status=503, content_type="text/plain; charset=utf-8")
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = 'attachment; filename="calendario_risco.csv"'
    resposta.write("\ufeff")
    w = csv.writer(resposta, delimiter=";")
    w.writerow(["Distrito", "Mês", "Atendimentos reativos por dia (média 2014-2024)", "Índice (mês / média do distrito)",
                "Ano mais calmo", "Média no ano mais calmo", "Ano mais intenso", "Média no ano mais intenso"])
    for m in meses:
        w.writerow([m["distrito"], m["mes"], m["media_dia"], m["indice"], m["ano_calmo"], m["media_ano_calmo"],
                    m["ano_intenso"], m["media_ano_intenso"]])
    return resposta

