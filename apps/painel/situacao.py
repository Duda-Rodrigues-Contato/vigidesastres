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
    for d in resultado:
        d["tom_24h"] = tom_chuva(d["chuva_24h_mm"])
        d["tom_prev"] = tom_chuva(d["previsao_24h_mm"])
        d["tom_72h"] = tom_acumulado(d["chuva_72h_mm"])
        d["celulas"] = [(d["chuva_24h_mm"], d["tom_24h"], d["estacao_24h"]),
                        (d["chuva_72h_mm"], d["tom_72h"], ""),
                        (d["previsao_24h_mm"], d["tom_prev"], "modelo")]
    return resultado


def tom_chuva(mm):
    """Cor da célula pela classe de chuva (limiares.py): vazio, amarelo, laranja ou vermelho."""
    if mm is None or mm < limiares.CHUVA_MODERADA:
        return ""
    if mm < limiares.CHUVA_FORTE:
        return "amarelo"
    return "laranja" if mm < limiares.CHUVA_MUITO_FORTE else "vermelho"


def tom_acumulado(mm):
    """Acumulado de 72 h: laranja a partir do solo encharcado, vermelho no dobro."""
    if mm is None or mm < limiares.SOLO_ENCHARCADO_MM:
        return ""
    return "laranja" if mm < 2 * limiares.SOLO_ENCHARCADO_MM else "vermelho"


def resumo_geral(distritos, avisos):
    """A resposta do topo do dashboard: precisa agir, onde e por quê, numa frase."""
    altos = [d for d in distritos if d["nivel"] == "ALTO"]
    medios = [d for d in distritos if d["nivel"] == "MÉDIO"]
    sem_dado = [d["nome"] for d in distritos if d["nivel"] == "SEM DADO"]
    nota = f" · {len(sem_dado)} distrito(s) sem dado: {', '.join(sem_dado)}" if 0 < len(sem_dado) < len(distritos) else ""
    if altos:
        return {"estado": "ALERTA", "cor": "vermelho",
                "titulo": "Risco alto em " + ", ".join(d["nome"] for d in altos),
                "frase": altos[0]["motivos"][0] + nota}
    if medios or avisos:
        if medios:
            titulo, frase = "Atenção em " + ", ".join(d["nome"] for d in medios), medios[0]["motivos"][0]
        else:
            titulo = "Atenção: aviso oficial do INMET"
            frase = f"{avisos[0].get('evento')} ({avisos[0].get('severidade')}) para a Região Metropolitana do Recife"
        return {"estado": "ATENÇÃO", "cor": "laranja", "titulo": titulo, "frase": frase + nota}
    if distritos and len(sem_dado) == len(distritos):
        return {"estado": "SEM DADOS", "cor": "cinza", "titulo": "Sem dados para avaliar",
                "frase": "As coletas não trouxeram chuva nem previsão. Rode python -m etl cemaden previsao."}
    return {"estado": "NORMAL", "cor": "verde", "titulo": "Nenhum gatilho acionado",
            "frase": "Chuva medida, previsão e maré dentro dos limiares, e nenhum aviso do INMET para o Recife." + nota}
