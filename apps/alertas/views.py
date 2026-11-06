"""Alertas e ações de resposta, lidos e gravados no PostgreSQL."""

import json
from datetime import date

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import AcaoResposta, Alerta


def _alerta_para_tela(a):
    quando = timezone.localtime(a.criado_em)
    return {"id": a.id, "severity": a.nivel, "title": a.titulo, "type": a.tipo, "area": a.distrito,
            "date": quando.strftime("%d/%m/%Y"), "time": quando.strftime("%H:%M"),
            "status": a.get_status_display(), "motivo": a.motivo, "origem": a.get_origem_display()}


def _acao_para_tela(a):
    return {"id": a.id, "name": a.nome, "team": a.equipe, "district": a.distrito,
            "date": a.data.strftime("%d/%m/%Y"), "status": a.get_status_display()}


def alertas_view(request):
    alertas = list(Alerta.objects.all()[:500])
    totais = {"total": len(alertas)}
    for s in Alerta.Status:
        totais[s.value] = sum(1 for a in alertas if a.status == s)
    return render(request, "alertas/alertas.html",
                  {"alertas": [_alerta_para_tela(a) for a in alertas], "totais": totais})


@require_POST
def alterar_status_alerta(request, pk):
    alerta = get_object_or_404(Alerta, pk=pk)
    status = json.loads(request.body or "{}").get("status")
    if status not in Alerta.Status.values:
        return JsonResponse({"erro": "status inválido"}, status=400)
    alerta.status = status
    alerta.save(update_fields=["status", "atualizado_em"])
    return JsonResponse(_alerta_para_tela(alerta))


def acoes_view(request):
    acoes = AcaoResposta.objects.all()[:500]
    return render(request, "alertas/acoes.html", {"acoes": [_acao_para_tela(a) for a in acoes]})


@require_POST
def criar_acao(request):
    dados = json.loads(request.body or "{}")
    status = {"Em andamento": AcaoResposta.Status.ANDAMENTO, "Concluída": AcaoResposta.Status.CONCLUIDA}.get(
        dados.get("status"), dados.get("status"))
    try:
        acao = AcaoResposta(nome=(dados.get("name") or "").strip(),
                            equipe=(dados.get("team") or "").strip() or "Equipe designada",
                            distrito=dados.get("district") or "", data=date.fromisoformat(dados.get("date") or ""),
                            status=status, alerta_id=dados.get("alerta") or None)
        acao.full_clean()
    except ValueError:
        return JsonResponse({"erro": "data inválida"}, status=400)
    except ValidationError as erro:
        return JsonResponse({"erro": " ".join(m for ms in erro.message_dict.values() for m in ms)}, status=400)
    acao.save()
    return JsonResponse(_acao_para_tela(acao), status=201)
