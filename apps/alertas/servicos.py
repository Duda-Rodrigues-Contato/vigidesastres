"""Gera os alertas do dia a partir dos gatilhos e dos avisos do INMET.

Roda depois do ETL (python manage.py gerar_alertas). Cada alerta tem uma
chave: rodar de novo no mesmo dia atualiza o alerta, não duplica. O status
(em aberto, monitorando, encerrado) é da equipe e nunca é sobrescrito.
"""

from django.utils import timezone

from apps.fontes import painel_chuva
from apps.fontes.resumo_mare import resumo_mare
from dominio import limiares

from .models import Alerta

NIVEL_INMET = {1: Alerta.Nivel.BAIXO, 2: Alerta.Nivel.MEDIO, 3: Alerta.Nivel.ALTO}


def _gravar(chave, **campos):
    alerta, criado = Alerta.objects.update_or_create(chave=chave, defaults=campos)
    return criado


def gerar_alertas(hoje=None):
    """Grava os alertas de hoje. Devolve {'novos': n, 'atualizados': n}."""
    hoje = hoje or timezone.localdate()
    novos = atualizados = 0

    distritos = painel_chuva.distritos_para_gatilhos()
    mare = resumo_mare()
    for a in (limiares.avaliar_gatilhos(distritos, mare) if distritos else []):
        criado = _gravar(
            f"gatilho:{a['tipo']}:{a['zona']}:{hoje.isoformat()}",
            titulo=f"{a['tipo']} — {a['zona']}", tipo=a["tipo"], nivel=a["nivel"], distrito=a["zona"],
            motivo=a["motivo"], origem=Alerta.Origem.GATILHO, dados={"gatilho": a, "data": hoje.isoformat()},
        )
        novos, atualizados = novos + criado, atualizados + (not criado)

    for aviso in painel_chuva.avisos_oficiais():
        criado = _gravar(
            f"inmet:{aviso['id']}",
            titulo=f"INMET: {aviso.get('evento')}", tipo="Aviso INMET",
            nivel=NIVEL_INMET.get(aviso.get("nivel"), Alerta.Nivel.BAIXO), distrito="Recife",
            motivo=aviso.get("descricao") or aviso.get("evento") or "",
            origem=Alerta.Origem.INMET,
            dados={"severidade": aviso.get("severidade"), "link": aviso.get("link"),
                   "inicio": str(aviso.get("inicio")), "fim": str(aviso.get("fim"))},
        )
        novos, atualizados = novos + criado, atualizados + (not criado)
    return {"novos": novos, "atualizados": atualizados}
