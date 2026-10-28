"""Classificação dos atendimentos da Defesa Civil: reativo ou rotina.

Reativo = a equipe foi acionada por um evento (lona, vistoria, alagamento,
deslizamento, imóvel com dano). Rotina = monitoramento, ação social,
porta-a-porta. Só o reativo serve para calibrar os gatilhos de chuva.

Critério (decisão 005): é reativo se
  - Ocorrencia veio preenchida (só ~3% vêm, e sempre descrevem um evento), ou
  - Solicitacao contém um dos termos abaixo.
Solicitacao vazia e sem Ocorrencia conta como rotina.
"""

from etl.comum.texto import normalizar

TERMOS_REATIVOS = ("LONA", "VISTORIA", "ALAGA", "DESLIZ", "BARREIRA", "DESABA", "DANO")
RISCOS = ("R1", "R2", "R3", "R4")


def eh_reativo(solicitacao, ocorrencia):
    if normalizar(ocorrencia or ""):
        return True
    s = normalizar(solicitacao or "")
    return any(t in s for t in TERMOS_REATIVOS)


def grau_de_risco(valor):
    """'r3 ' -> 'R3'; vazio ou fora da escala -> None."""
    v = normalizar(valor or "")
    return v if v in RISCOS else None
