"""Unidades do modelo de eventos: os 8 distritos do Recife e 6 municípios vizinhos.

Os vizinhos entram para aumentar os exemplos de eventos (o REINDESC tem 80 dias com
evento no Recife e 374 município-dias na região): a geografia é a mesma (morros e
planície costeira). O resultado que decide é sempre o do Recife.
"""

from dominio.distritos import nome_distrito

# IBGE (7 dígitos) -> (nome como no REINDESC, prefixo do código das estações do CEMADEN, lon, lat do centro)
VIZINHOS = {
    "2607901": ("JABOATÃO DOS GUARARAPES", "260790", -34.99, -8.15),
    "2609600": ("OLINDA", "260960", -34.86, -8.01),
    "2603454": ("CAMARAGIBE", "260345", -34.99, -8.02),
    "2610707": ("PAULISTA", "261070", -34.87, -7.94),
    "2602902": ("CABO DE SANTO AGOSTINHO", "260290", -35.04, -8.29),
    "2613701": ("SÃO LOURENÇO DA MATA", "261370", -35.02, -8.00),
}
RECIFE = "2611606"
PREFIXO_RECIFE = "261160"


def unidade_do_distrito(codigo):
    return nome_distrito(codigo)


def unidade_da_estacao(codestacao, distrito_codigo=None):
    """'DS III' para estação do Recife (pelo distrito), nome do município para as vizinhas."""
    if codestacao.startswith(PREFIXO_RECIFE):
        return nome_distrito(distrito_codigo) if distrito_codigo else None
    for nome, prefixo, _, _ in VIZINHOS.values():
        if codestacao.startswith(prefixo):
            return nome
    return None


def unidades():
    """Todas as unidades, na ordem: distritos do Recife e depois os vizinhos."""
    return [nome_distrito(c) for c in range(1, 9)] + [v[0] for v in VIZINHOS.values()]


def eh_recife(unidade):
    return unidade.startswith("DS ")
