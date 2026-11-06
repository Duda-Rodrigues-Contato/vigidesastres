"""Saúde dos dados: há quanto tempo cada fonte foi coletada, e se deu certo.

Uma fonte é "atrasada" se a última coleta passou do prazo esperado para ela
(diárias: 26 h; InfoDengue, semanal: 8 dias), e "com erro" se a última falhou.
"""

from datetime import datetime, timezone

from apps.fontes.repositorios import execucoes

FONTES = {  # nome no ETL -> (rótulo na tela, prazo em horas)
    "cemaden": ("Chuva medida", 26),
    "previsao": ("Previsão", 26),
    "mare": ("Maré", 26),
    "avisos_inmet": ("Avisos INMET", 26),
    "infodengue": ("InfoDengue", 24 * 8),
}


def _idade(horas):
    if horas < 1:
        return "agora há pouco"
    if horas < 48:
        return f"há {int(horas)} h"
    return f"há {int(horas // 24)} dias"


def saude_dos_dados(agora=None):
    agora = agora or datetime.now(timezone.utc)
    ultimas = execucoes.ultimas(FONTES)
    itens = []
    for fonte, (rotulo, prazo) in FONTES.items():
        r = ultimas.get(fonte)
        if not r or not r["quando"]:
            itens.append({"rotulo": rotulo, "texto": "nunca coletada", "estado": "erro", "detalhe": ""})
            continue
        horas = (agora - r["quando"]).total_seconds() / 3600
        estado = "erro" if r["status"] != "ok" else ("atrasada" if horas > prazo else "ok")
        texto = _idade(horas) + (" (falhou)" if estado == "erro" else "")
        itens.append({"rotulo": rotulo, "texto": texto, "estado": estado, "detalhe": r.get("erro") or ""})
    return itens
