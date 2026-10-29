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
# classificação final que só existe numa doença (SINAN): 13 = chikungunya
CLASSE_EXCLUSIVA = {"13": "chikungunya"}


def doenca_pela_classificacao(doenca, classes):
    """Se a maioria das linhas tem a classe exclusiva de OUTRA doença, devolve essa
    doença (o arquivo publicado está trocado); senão, None.

    Caso real: o arquivo "zika 2021" do portal é idêntico ao de chikungunya 2021.
    """
    total = sum(classes.values()) or 1
    for classe, dona in CLASSE_EXCLUSIVA.items():
        if dona != doenca and classes.get(classe, 0) / total > 0.5:
            return dona
    return None
