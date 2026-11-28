from dominio import calor


def test_indice_de_calor_bate_com_a_tabela_do_nws():
    assert calor.indice_de_calor(31, 60) == 34.8          # tabela NWS: ~95 °F (35 °C)
    assert abs(calor.indice_de_calor(25, 80) - 25) < 1    # abaixo de 27 °C, quase a temperatura
    assert calor.indice_de_calor(None, 60) is None


def test_faixas():
    assert calor.faixa(30) == "Cautela" and calor.faixa(35) == "Cautela extrema"
    assert calor.faixa(45) == "Perigo" and calor.faixa(20) == "Normal"


def test_alerta_pede_persistencia_para_medio_e_pico_para_alto():
    a = calor.avaliar_calor([
        {"nome": "DS I", "indice_calor_max_24h_c": 35, "horas_cautela_extrema_24h": 2},   # pico curto: nada
        {"nome": "DS II", "indice_calor_max_24h_c": 35, "horas_cautela_extrema_24h": 3},  # MÉDIO
        {"nome": "DS III", "indice_calor_max_24h_c": 42, "horas_cautela_extrema_24h": 1},  # ALTO
        {"nome": "DS IV", "indice_calor_max_24h_c": None}])
    assert [(x["zona"], x["nivel"]) for x in a] == [("DS II", "MÉDIO"), ("DS III", "ALTO")]
