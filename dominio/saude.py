"""Quais unidades de saúde entram no mapa de emergência.

Tipos que importam numa emergência climática: quem atende, interna ou se
desloca. Fica de fora consultório isolado, laboratório privado, farmácia e
afins - a maior parte do cadastro, que poluiria o mapa sem ajudar na decisão.
Códigos do catálogo CNES (endpoint /cnes/tipounidades).
"""

TIPOS_RESPOSTA = {
    1,   # POSTO DE SAÚDE
    2,   # CENTRO DE SAÚDE/UNIDADE BÁSICA (UBS)
    4,   # POLICLÍNICA
    5,   # HOSPITAL GERAL
    7,   # HOSPITAL ESPECIALIZADO
    15,  # UNIDADE MISTA
    20,  # PRONTO SOCORRO GERAL
    21,  # PRONTO SOCORRO ESPECIALIZADO
    40,  # UNIDADE MÓVEL TERRESTRE
    42,  # UNIDADE MÓVEL PRÉ-HOSPITALAR (SAMU)
    50,  # UNIDADE DE VIGILÂNCIA EM SAÚDE (estrutura do Vigidesastres)
    61,  # CENTRO DE PARTO NORMAL
    62,  # HOSPITAL/DIA
    69,  # CENTRO DE ATENÇÃO HEMOTERAPIA
    70,  # CENTRO DE ATENÇÃO PSICOSSOCIAL (CAPS)
    71,  # CENTRO DE APOIO À SAÚDE DA FAMÍLIA
    73,  # PRONTO ATENDIMENTO (UPA)
    85,  # CENTRO DE IMUNIZAÇÃO (resposta pós-inundação)
}
