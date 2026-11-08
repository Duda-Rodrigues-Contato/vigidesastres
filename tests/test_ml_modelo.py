import random
from datetime import datetime, timedelta

import pandas as pd

from ml import dados, treinar
from ml.modelo import ENTRADAS, ModeloRisco

GRADES_PEQUENAS = {"arvore": {"max_depth": [3], "min_samples_leaf": [20]},
                   "xgboost": {"n_estimators": [30], "max_depth": [3], "learning_rate": [0.1]}}


def _tabela():
    random.seed(7)
    linhas = []
    for distrito in (3, 6):
        d = datetime(2015, 1, 1)
        while d <= datetime(2024, 12, 31):
            chuva = max(0.0, random.gauss(8 if d.month in (4, 5, 6) else 2, 12))
            linha = {c: 0 for c in ENTRADAS}
            linha.update({"distrito_codigo": distrito, "data": d, "ano": d.year, "mes": d.month,
                          "dia_semana": d.weekday(), "chuva_dia_mm": chuva, "chuva_3d_mm": chuva * 2,
                          "mare_max_m": 1.5, "atendimentos_chuva": int(chuva // 2) * 4 + int(random.random() * 2),
                          "atendimentos_alagamento": 0})
            linhas.append(linha)
            d += timedelta(1)
    return dados.preparar(pd.DataFrame(linhas))


def test_treino_completo_compara_e_vence_o_acaso(tmp_path, monkeypatch):
    monkeypatch.setattr("ml.modelo.PASTA", tmp_path)
    resultados, escolhido = treinar.executar(_tabela(), grades=GRADES_PEQUENAS, avisar=lambda s: None)
    assert {"Árvore de decisão", "XGBoost", "XGBoost SEM chuva (controle)", "Limiares atuais (MÉDIO+)"} <= set(resultados)
    assert resultados["XGBoost"]["f1"] > resultados["XGBoost SEM chuva (controle)"]["f1"]   # no simulado, a chuva manda
    assert 0 < escolhido.limiar < 1
    assert resultados["XGBoost"]["recall"] > 0.5                  # a chuva explica o alvo simulado
    salvo = ModeloRisco.carregar()
    assert salvo.limiar == escolhido.limiar and salvo.pacote["alvo"]["fator"] == 3
    assert "dia_semana" not in ENTRADAS and "fim_de_semana" not in ENTRADAS


def test_pico_compara_com_a_rotina_e_usa_tres_dias():
    linhas = []
    d0 = datetime(2019, 1, 1)
    for n in range(60):
        d = d0 + timedelta(n)
        campanha = 6 if 20 <= n < 45 else 1          # rotina sobe numa campanha de lonas
        atend = 30 if n == 50 else (8 if n == 17 else campanha)   # dia 17: 8 numa rotina de 1 não é evento
        linhas.append({"distrito_codigo": 3, "data": d, "ano": 2019, "atendimentos_chuva": atend})
    df = dados.marcar_pico(pd.DataFrame(linhas)).set_index("data")
    assert df.loc[d0 + timedelta(50), "critico"] and df.loc[d0 + timedelta(48), "critico"]   # o pico entra na janela
    assert not df.loc[d0 + timedelta(30):d0 + timedelta(40), "critico"].any()                # campanha não é pico
    assert not df.loc[d0 + timedelta(5), "critico"]                                          # sem rotina ainda: não marca
    assert not df.loc[d0 + timedelta(15):d0 + timedelta(17), "critico"].any()                # 8 < rotina + 10
    assert not df.loc[d0 + timedelta(18):d0 + timedelta(22), "critico"].any()                # início da campanha (6) também não


def test_veredito_exige_vencer_o_controle_e_os_limiares():
    base = {"Limiares atuais (só ALTO)": {"f1": 0.20}, "Limiares atuais (MÉDIO+)": {"f1": 0.14},
            "XGBoost SEM chuva (controle)": {"f1": 0.11}}
    assert treinar.veredito({**base, "XGBoost": {"f1": 0.30}}, "XGBoost")[0]
    assert not treinar.veredito({**base, "XGBoost": {"f1": 0.12}}, "XGBoost")[0]      # empata com o controle
    assert not treinar.veredito({**base, "XGBoost": {"f1": 0.19}}, "XGBoost")[0]      # perde para os limiares


def test_alvo_fisico_usa_so_alagamento_e_deslizamento():
    linhas = [{"distrito_codigo": 3, "data": datetime(2019, 1, 1) + timedelta(n), "ano": 2019,
               "atendimentos_chuva": 50, "atendimentos_alagamento": 6 if n == 40 else 0,
               "atendimentos_deslizamento": 0, "chuva_3d_mm": 0.0, "mare_max_m": 1.0} for n in range(60)]
    df = dados.marcar_pico(dados.preparar(pd.DataFrame(linhas)), "fisico").set_index("data")
    assert df.loc[datetime(2019, 2, 10), "critico"]                  # 6 alagamentos numa rotina de 0
    assert df["critico"].sum() == 3                                   # D-2, D-1 e D (janela de 3 dias)
