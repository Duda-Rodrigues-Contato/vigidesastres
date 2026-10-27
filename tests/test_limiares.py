import pytest

from dominio import limiares

MARE_ALTA = {"alta_prevista": True, "nivel_m": 1.12, "quando": "18/10 às 14:00"}
MARE_BAIXA = {"alta_prevista": False, "nivel_m": 0.40, "quando": "18/10 às 02:00"}


@pytest.mark.parametrize("mm, classe", [
    (0.0, "Seco"), (2.2, "Chuva muito fraca"), (8.4, "Chuva moderada"),
    (18.6, "Chuva forte"), (55.3, "Chuva muito forte"),
])
def test_classes_nas_fronteiras_da_tese(mm, classe):
    assert limiares.classificar_chuva(mm) == classe


def _avaliar(prev, acum, mare):
    zona = {"nome": "Zona X", "chuva_prox_24h_mm": prev, "chuva_72h_mm": acum}
    return {(a["tipo"], a["nivel"]) for a in limiares.avaliar_gatilhos([zona], mare)}


def test_dia_seco_nao_gera_alerta():
    assert _avaliar(0.3, 0.0, MARE_ALTA) == set()


def test_mare_alta_transforma_chuva_moderada_em_alerta_de_alagamento():
    assert _avaliar(12.4, 0.0, MARE_BAIXA) == set()
    assert _avaliar(12.4, 0.0, MARE_ALTA) == {("Alagamento", "MÉDIO")}


def test_solo_encharcado_agrava_so_o_deslizamento():
    assert _avaliar(6.0, 35.0, MARE_BAIXA) == {("Deslizamento", "MÉDIO")}


def test_sem_dado_de_mare_nao_presume_mare_alta():
    assert _avaliar(12.4, 0.0, None) == set()
