"""Situação de cada distrito: a mesma resposta para o mapa e para o dashboard.

Nível = o pior gatilho do distrito (dominio/limiares.py), com chuva medida
(CEMADEN, pior estação) e previsão (Open-Meteo). Junta os alertas que a equipe
ainda acompanha (PostgreSQL). Um distrito sem nenhum dado fica "SEM DADO",
nunca "NORMAL": falta de dado não é ausência de risco.
"""

from apps.alertas.models import Alerta
from apps.fontes import painel_chuva
from apps.fontes.repositorios import chuva as repo_chuva
from apps.fontes.resumo_mare import resumo_mare
from dominio import limiares
from dominio.distritos import ROMANOS, nome_distrito

ORDEM = {"ALTO": 0, "MÉDIO": 1, "NORMAL": 2, "SEM DADO": 3}


def situacao_por_distrito():
    distritos = painel_chuva.distritos_para_gatilhos()
    por_nome = {d["nome"]: d for d in distritos}
    gatilhos = limiares.avaliar_gatilhos(distritos, resumo_mare()) if distritos else []

    ultima = repo_chuva.ultima_leitura()
    pior24 = painel_chuva.pior_estacao_por_distrito(24, ultima) if ultima else {}

    abertos = {}
    for d in Alerta.objects.exclude(status=Alerta.Status.ENCERRADO).values_list("distrito", flat=True):
        abertos[d] = abertos.get(d, 0) + 1

    resultado = []
    for codigo in range(1, len(ROMANOS) + 1):
        nome = nome_distrito(codigo)
        dados = por_nome.get(nome, {})
        meus = [g for g in gatilhos if g["zona"] == nome]
        estacao = pior24.get(codigo)
        tem_dado = estacao is not None or dados.get("chuva_prox_24h_mm") is not None
        if meus:
            nivel = "ALTO" if any(g["nivel"] == "ALTO" for g in meus) else "MÉDIO"
        else:
            nivel = "NORMAL" if tem_dado else "SEM DADO"
        resultado.append({
            "codigo": codigo,
            "nome": nome,
            "nivel": nivel,
            "motivos": [g["motivo"] for g in meus],
            "chuva_24h_mm": estacao["chuva_mm"] if estacao else None,
            "estacao_24h": estacao["nome"] if estacao else None,
            "chuva_72h_mm": dados.get("chuva_72h_mm"),
            "previsao_24h_mm": dados.get("chuva_prox_24h_mm"),
            "alertas_abertos": abertos.get(nome, 0),
        })
    return resultado
