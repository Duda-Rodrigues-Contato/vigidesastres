import math
import random
from datetime import datetime, timedelta

import pandas as pd
import pytest

from ml import dengue_clima, perfis

GRADE = {"n_estimators": [80], "max_depth": [3], "learning_rate": [0.1]}


def test_dengue_clima_detecta_quando_a_temperatura_antecede_os_casos():
    random.seed(4)
    semanas = pd.date_range("2013-06-02", "2024-12-29", freq="7D")
    temp = [26 + 2 * math.sin(2 * math.pi * i / 52) + random.gauss(0, 1.2) for i in range(len(semanas))]
    casos = [max(1.0, 30 + 25 * (sum(temp[max(0, i - 8):i - 3]) / 5 - 26) + random.gauss(0, 3)) if i > 8 else 30
             for i in range(len(semanas))]
    dengue = pd.DataFrame({"inicio_semana": semanas, "casos_est": casos})
    dias = pd.date_range("2013-06-01", "2025-01-10")
    t_dia = {d: temp[min(len(temp) - 1, (d - semanas[0]).days // 7)] for d in dias}
    clima = pd.DataFrame({"data": dias, "temp_media_c": [t_dia[d] for d in dias], "umidade_ar_pct": 80.0})
    chuva = pd.DataFrame({"data": dias, "chuva_dia_mm": 3.0})
    aprovado, erros = dengue_clima.executar(dengue_clima.montar(dengue, clima, chuva), GRADE, avisar=lambda t: None)
    assert aprovado and erros["com clima"] < erros["sem clima"]


def test_perfis_separam_encosta_de_planicie():
    random.seed(1)
    bairros, dc, eventos, vul = {}, {}, {}, {}
    for i in range(30):
        tipo = ["encosta", "planicie", "baixo"][i % 3]
        chave = f"B{i}"
        bairros[chave] = {"nome": chave, "populacao": 10_000, "area_km2": 2, "distrito_codigo": 1}
        dc[chave] = {"deslizamento": 300 if tipo == "encosta" else 5, "alagamento": 200 if tipo == "planicie" else 3,
                     "lona": 400 if tipo == "encosta" else 10, "vistoria": 20}
        eventos[chave] = {"Geo": 6 if tipo == "encosta" else 0, "Hidro": 4 if tipo == "planicie" else 0}
        vul[chave] = {"pct_pop_comunidades": 0.5 if tipo != "baixo" else 0.05, "risco_comunidades": 5, "areas_risco": 3}
    df, k, silhueta, _ = perfis.agrupar(perfis.caracteristicas(bairros, dc, eventos, vul), ks=range(3, 5))
    assert k == 3 and silhueta > 0.4
    grupo = dict(zip(df["chave"], df["perfil"]))
    assert grupo["B0"] == grupo["B3"] != grupo["B1"]                      # encostas juntas, planície à parte
    assert grupo["B0"].startswith("encosta") and "alagamentos" in grupo["B1"] and grupo["B2"] == "baixo risco"


def test_bairro_pequeno_nao_vira_grupo_sozinho():
    random.seed(1)
    bairros, dc, eventos, vul = {}, {}, {}, {}
    for i in range(30):
        tipo = ["encosta", "planicie", "baixo"][i % 3]
        bairros[f"B{i}"] = {"nome": f"B{i}", "populacao": 10_000 + i * 100, "area_km2": 2, "distrito_codigo": 1}
        dc[f"B{i}"] = {"deslizamento": 300 if tipo == "encosta" else 5, "alagamento": 200 if tipo == "planicie" else 3,
                       "lona": 400 if tipo == "encosta" else 10, "vistoria": 20}
        eventos[f"B{i}"] = {}
        vul[f"B{i}"] = {}
    bairros["MINI"] = {"nome": "MINI", "populacao": 600, "area_km2": 0.5, "distrito_codigo": 1}
    dc["MINI"] = {"vistoria": 900}
    df, k, _, _ = perfis.agrupar(perfis.caracteristicas(bairros, dc, eventos, vul))
    assert df.groupby("perfil").size().min() >= perfis.MINIMO_POR_GRUPO


@pytest.mark.django_db
def test_api_dos_perfis(client, destino, monkeypatch):
    from apps.fontes.repositorios import conexao
    destino.banco["silver_bairros"].insert_one({"chave": "IBURA", "nome": "Ibura", "geometria": {"type": "Point", "coordinates": [0, 0]}})
    destino.banco["gold_perfil_bairro"].insert_one({"chave": "IBURA", "perfil": "encosta com deslizamentos", "grupo": 0})
    monkeypatch.setattr(conexao, "banco", lambda: destino.banco)
    assert client.get("/api/perfis/").json()["features"][0]["properties"]["perfil"] == "encosta com deslizamentos"
