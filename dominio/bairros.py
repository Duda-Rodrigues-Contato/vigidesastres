"""Correspondência entre nomes de bairro usados nas fontes e os oficiais."""

# Plano de Contingência 2024 da Defesa Civil: nomes que não são bairros
# oficiais (ou vêm abreviados) -> bairro(s) oficial(is)
APELIDOS_PLANO = {
    "C. DO BARRETO": ["CAMPINA DO BARRETO"],
    "BREJO BEBERIBE": ["BREJO DE BEBERIBE"],
    "IBURA DE BAIXO": ["IBURA"],  # Ibura de Baixo é parte do bairro Ibura
    "SETUBAL": ["BOA VIAGEM"],  # Setúbal é parte do bairro Boa Viagem
    "CORDEIRO / MADALENA": ["CORDEIRO", "MADALENA"],  # área na divisa
}
