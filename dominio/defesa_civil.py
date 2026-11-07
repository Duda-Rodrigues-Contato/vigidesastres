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

# alvo do modelo de risco (decisão 009): só o que é ligado à chuva. Vistorias e
# monitoramento de imóveis ficam de fora: no centro (DS I) são casarões antigos
# vistoriados na estação seca, sem relação com o clima.
TERMOS_CHUVA = ("LONA", "ALAGA", "INUNDA", "DESLIZ", "BARREIRA")

# erros de acento herdados dos arquivos do portal (2022 vem em Windows-1252)
CORRECOES = {"IMVEIS": "IMOVEIS"}


def eh_reativo(solicitacao, ocorrencia):
    if normalizar(ocorrencia or ""):
        return True
    s = normalizar(solicitacao or "")
    return any(t in s for t in TERMOS_REATIVOS)


def texto_tipo(valor):
    """Solicitação ou ocorrência normalizada, com os erros de acento conhecidos corrigidos."""
    t = normalizar(valor or "")
    for errado, certo in CORRECOES.items():
        t = t.replace(errado, certo)
    return t


def ligado_a_chuva(solicitacao, ocorrencia):
    """O atendimento é resposta a um efeito da chuva? Olha a solicitação E a ocorrência."""
    texto = texto_tipo(solicitacao) + " " + texto_tipo(ocorrencia)
    return any(t in texto for t in TERMOS_CHUVA)


def grau_de_risco(valor):
    """'r3 ' -> 'R3'; vazio ou fora da escala -> None."""
    v = normalizar(valor or "")
    return v if v in RISCOS else None
