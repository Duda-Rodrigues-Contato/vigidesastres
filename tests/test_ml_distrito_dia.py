from datetime import date, timedelta

from dominio.feriados import feriados_recife
from etl.derivados import ml_distrito_dia as ml

D0 = date(2019, 6, 10)


def _montar(estacao_dia, inmet=None, alvo=None):
    return ml.montar(estacao_dia, {"A": 3, "B": 3, "C": 6}, inmet or {}, {D0: (1.1, 2.2)}, alvo or {},
                     {3: {"comunidades": 40}}, D0, D0 + timedelta(2))


def test_pior_estacao_valida_e_acumulados():
    estacao = {}
    for n in range(-7, 3):
        dia = D0 + timedelta(n)
        estacao[("A", dia)] = (10.0, 3.0, 24)
        estacao[("B", dia)] = (30.0, 9.0, 5)        # poucas leituras: não conta, mesmo sendo maior
    linhas = {(l["distrito_codigo"], l["data"].date()): l for l in _montar(estacao)}
    l = linhas[(3, D0)]
    assert (l["chuva_dia_mm"], l["chuva_3d_mm"], l["chuva_7d_mm"], l["fonte_chuva"]) == (10.0, 30.0, 70.0, "cemaden")
    assert (l["mare_max_m"], l["comunidades"]) == (1.1, 40)
    assert linhas[(5, D0)]["chuva_dia_mm"] is None                  # distrito sem estação e sem INMET


def test_inmet_cobre_o_distrito_sem_estacao_valida():
    inmet = {D0 + timedelta(n): (4.0, 1.0, 24) for n in range(-7, 3)}
    l = {(x["distrito_codigo"], x["data"].date()): x for x in _montar({}, inmet)}[(5, D0)]
    assert (l["chuva_dia_mm"], l["fonte_chuva"]) == (4.0, "inmet")


def test_alvo_contexto_e_calendario():
    linhas = _montar({}, alvo={(3, D0): (12, 20, 4, 6)})
    l = next(x for x in linhas if x["distrito_codigo"] == 3 and x["data"].date() == D0)
    assert (l["atendimentos_chuva"], l["atendimentos_reativos"]) == (12, 20)
    assert (l["atendimentos_alagamento"], l["atendimentos_deslizamento"]) == (4, 6)
    assert len(linhas) == 8 * 3 and l["dia_semana"] == 0 and not l["pandemia"]


def test_feriados_do_recife():
    f = feriados_recife(2024)
    assert date(2024, 2, 12) in f and date(2024, 2, 13) in f        # carnaval de 2024
    assert date(2024, 6, 24) in f and date(2024, 7, 16) in f and date(2024, 12, 25) in f



def test_hora_do_pico_vem_da_estacao_com_a_hora_mais_forte():
    from datetime import datetime
    estacao = {("A", D0): (40.0, 8.0, 24, datetime(2019, 6, 10, 15)), ("B", D0): (30.0, 20.0, 24, datetime(2019, 6, 10, 9))}
    l = {(x["distrito_codigo"], x["data"].date()): x for x in _montar(estacao)}[(3, D0)]
    assert (l["chuva_dia_mm"], l["chuva_pico_mm"], l["hora_pico_utc"]) == (40.0, 20.0, datetime(2019, 6, 10, 9))
