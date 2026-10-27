"""Regras de negócio das arboviroses (CRISP-DM, fase 4)."""

# Níveis do InfoDengue, conforme a documentação do sistema (Fiocruz/FGV)
NIVEIS_INFODENGUE = {
    1: ("Verde", "condições climáticas desfavoráveis à transmissão"),
    2: ("Amarelo", "clima favorável ao mosquito e à transmissão"),
    3: ("Laranja", "transmissão aumentada e sustentada"),
    4: ("Vermelho", "incidência acima de 90% do histórico"),
}

DOENCAS = ("dengue", "chikungunya", "zika")


def nome_do_nivel(nivel):
    return NIVEIS_INFODENGUE.get(nivel, ("--", ""))
