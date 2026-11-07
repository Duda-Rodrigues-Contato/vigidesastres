from datetime import datetime, timedelta

import pandas as pd

from ml import dados, linha_base, metricas


def _tabela():
    linhas = []
    for distrito in (3, 6):
        d = datetime(2015, 1, 1)
        while d <= datetime(2024, 12, 31):
            chuva = 60.0 if d.day == 15 else 1.0
            linhas.append({"distrito_codigo": distrito, "data": d, "ano": d.year, "chuva_dia_mm": chuva,
                           "chuva_3d_mm": chuva * 1.5, "mare_max_m": 1.0 + (d.day % 15) / 15,
                           "atendimentos_chuva": (40 if distrito == 3 else 8) if d.day == 15 else 1,
                           "atendimentos_alagamento": 0})
            d += timedelta(1)
    return dados.preparar(pd.DataFrame(linhas))


def test_corte_vem_so_do_treino_e_respeita_o_minimo():
    df = _tabela()
    df.loc[df["ano"] >= 2022, "atendimentos_chuva"] = 999          # mexer no teste não pode mudar o corte
    cortes = dados.cortes_do_treino(df)
    assert cortes[3] == 5 and cortes[6] == 5                       # p95 = 1, então vale o mínimo


def test_acumulado_usa_so_dias_anteriores():
    df = _tabela()
    dia15 = df[(df["distrito_codigo"] == 3) & (df["data"] == datetime(2015, 1, 15))].iloc[0]
    assert dia15["acumulado_72h_antes"] == 1.5                     # o próprio dia 15 (90 mm) não entra


def test_linha_base_e_metricas():
    df = dados.marcar_critico(_tabela(), {3: 5, 6: 5})
    previsto = linha_base.prever(df)
    m = metricas.resumo(df["critico"], previsto)
    assert m["recall"] == 1.0                                      # 60 mm de chuva: todo dia crítico é alertado
    assert m["precisao"] == 1.0 and "recall 100%" in metricas.texto("x", m)
