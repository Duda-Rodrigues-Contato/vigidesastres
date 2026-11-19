import random
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from ml import demanda

GRADE = {"n_estimators": [80], "max_depth": [3], "learning_rate": [0.1]}


def _diario():
    """Chuva em períodos (semanas secas e chuvosas que se repetem); a demanda depende da chuva
    das duas semanas ANTERIORES (solo encharcado) e de vistorias que não dependem de chuva."""
    random.seed(2)
    linhas, d, chuvoso, historico = [], datetime(2015, 1, 1), False, []
    while d <= datetime(2024, 12, 31):
        if d.weekday() == 0:
            chuvoso = random.random() < (0.8 if chuvoso else 0.2 + 0.3 * (d.month in (4, 5, 6, 7)))
        chuva = max(0.0, random.gauss(25 if chuvoso else 1, 8))
        historico.append(chuva)
        acumulado = sum(historico[-21:-7])
        for dist in (2, 7):
            ligados = max(0, int(random.gauss(acumulado * dist / 40, 2)))
            outros = max(0, int(random.gauss(6 * dist / 4 * (d.month in (11, 12, 1)) + 3, 2)))
            linhas.append({"distrito_codigo": dist, "data": d, "chuva_dia_mm": chuva,
                           "atendimentos_reativos": ligados + outros, "atendimentos_chuva": ligados})
        d += timedelta(1)
    return pd.DataFrame(linhas)


def test_entradas_usam_so_o_passado():
    s = demanda.semanal(_diario())
    assert set(s["dias"]) == {7}
    g = s[s["distrito_codigo"] == 2].reset_index(drop=True)
    assert g.loc[5, "atend_ant_1"] == g.loc[4, "atendimentos"]
    assert g.loc[5, "chuva_2sem_mm"] == g.loc[3:4, "chuva_semana_mm"].sum()
    assert (s["atend_chuva"] + s["atend_outros"] == s["atendimentos"]).all()
    for nome, (entradas, _) in demanda.VERSOES.items():
        if nome != demanda.ORIGINAL:
            assert "chuva_semana_mm" not in entradas and "atendimentos" not in entradas


def test_buraco_na_serie_nao_vira_semana_anterior():
    df = _diario()
    falta = pd.Timestamp("2016-03-09")                       # quarta-feira: a semana fica incompleta
    s = demanda.semanal(df[~((df["data"] == falta) & (df["distrito_codigo"] == 2))])
    seguinte = s[(s["distrito_codigo"] == 2) & (s["inicio"] == pd.Timestamp("2016-03-14"))].iloc[0]
    assert np.isnan(seguinte["atend_ant_1"]) and not np.isnan(seguinte["atend_media_4"])


def test_demanda_aprovada_quando_o_passado_explica():
    aprovado, mae_m, mae_r = demanda.executar(demanda.semanal(_diario()), GRADE, avisar=lambda t: None)
    assert aprovado and mae_m < mae_r


def test_metricas():
    m = demanda.metricas(np.array([10.0, 20.0, np.nan]), np.array([12.0, 18.0, 5.0]))
    assert m["mae"] == 2.0 and abs(m["wape"] - 4 / 30) < 1e-9


def _pacote():
    return demanda.treinar_final(demanda.semanal(_diario()), GRADE)


def test_previsao_completa_quando_ha_semana_passada():
    docs = demanda.prever(_diario(), _pacote(), hoje=date(2024, 12, 25))
    assert {d["distrito_codigo"] for d in docs} == {2, 7}
    assert all(d["completa"] and d["previsto"] > 0 and d["inicio_semana"] == "2024-12-23" for d in docs)


def test_previsao_cai_para_o_calendario_com_dados_atrasados():
    docs = demanda.prever(_diario(), _pacote(), hoje=date(2026, 11, 19))
    assert docs and all(not d["completa"] and d["versao"] == demanda.REDUZIDA for d in docs)
    assert docs[0]["dados_ate"] == "2024-12-31" and docs[0]["normal"] is not None
    assert demanda.prever(_diario().iloc[0:0], _pacote(), hoje=date(2026, 11, 19))  # banco vazio não quebra


def test_tela_do_calendario_mostra_a_previsao(client, destino, monkeypatch):
    from apps.fontes.repositorios import conexao
    from etl.destinos.base import Carga
    docs = demanda.prever(_diario(), _pacote(), hoje=date(2026, 11, 19))
    destino.carregar(Carga("gold.demanda_previsao", docs))
    destino.banco["gold_calendario_risco_mes"].insert_one({"distrito_codigo": 2, "distrito": "DS II", "mes": 1,
        "media_dia": 1, "indice": 1, "ano_calmo": 2015, "media_ano_calmo": 1, "ano_intenso": 2016,
        "media_ano_intenso": 2})
    monkeypatch.setattr(conexao, "banco", lambda: destino.banco)
    html = client.get("/calendario/").content.decode()
    assert "semana de 16/11/2026 a 22/11/2026" in html and "vão até 31/12/2024" in html and "DS VII" in html
