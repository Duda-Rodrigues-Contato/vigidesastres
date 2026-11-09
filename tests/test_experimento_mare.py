import math
import random
from datetime import datetime, timedelta

import pandas as pd

from ml import experimento_mare as em

GRADE = {"n_estimators": [60], "max_depth": [3], "learning_rate": [0.1]}


def _dados(mare_importa):
    """Alagamento quando chove forte E (se mare_importa) a maré na hora do pico está alta."""
    random.seed(3)
    tabela, gtsm, horas = [], [], []
    d = datetime(2015, 1, 1)
    while d <= datetime(2024, 12, 31):
        chuva = max(0.0, random.gauss(6, 14))
        pico = d + timedelta(hours=random.randint(0, 23))
        nivel = 1.2 + 1.0 * math.cos(2 * math.pi * (pico - datetime(2015, 1, 1)).total_seconds() / 3600 / 12.42)
        horas.append({"hora": pico.replace(minute=0), "nivel_m": nivel})
        alaga = chuva > 25 and (nivel > 1.6 or not mare_importa) and random.random() < 0.9
        gtsm.append({"data": d, "nivel_total_max_m": 2.2 + random.gauss(0, .05), "ressaca_max_m": abs(random.gauss(.08, .02))})
        for dist in (1, 6):
            tabela.append({"distrito_codigo": dist, "data": d, "ano": d.year, "mes": d.month, "chuva_dia_mm": chuva,
                           "hora_pico_utc": pico, "chuva_pico_mm": chuva / 3,
                           "chuva_vespera_mm": None, "chuva_3d_mm": chuva, "chuva_7d_mm": None, "max_hora_mm": chuva / 3,
                           "mare_max_m": 2.2, "mare_amplitude_m": 2.0, "atendimentos_alagamento": int(alaga),
                           "atendimentos_chuva": 0})
        d += timedelta(1)
    tab = em.dados.preparar(pd.DataFrame(tabela))
    return em.montar(tab, pd.DataFrame(gtsm), pd.DataFrame(horas))


def test_detecta_a_mare_na_hora_da_chuva_quando_ela_importa():
    df = _dados(mare_importa=True)
    assert em.rodar(df, em.EXPERIMENTOS["B"], GRADE, avisar=lambda s: None) is True


def test_nao_inventa_efeito_quando_a_mare_nao_importa():
    df = _dados(mare_importa=False)
    assert em.rodar(df, em.EXPERIMENTOS["B"], GRADE, avisar=lambda s: None) is False



def test_bootstrap_sorteia_dias_e_mede_a_incerteza():
    import numpy as np
    rng = np.random.default_rng(0)
    dias = np.repeat(np.arange(300), 2)                      # 2 distritos por dia
    y = rng.random(600) < 0.1
    bom, ruim = y * 0.8 + rng.random(600) * 0.2, rng.random(600)
    (baixo, alto), acima_zero, _ = em.bootstrap_diferenca(y, bom, ruim, dias, repeticoes=200)
    assert baixo > 0 and acima_zero == 1.0                   # diferença clara: o intervalo não cruza o zero
    (baixo, alto), acima_zero, _ = em.bootstrap_diferenca(y, ruim, ruim, dias, repeticoes=200)
    assert baixo <= 0 <= alto                                # sem diferença: o intervalo cruza o zero
