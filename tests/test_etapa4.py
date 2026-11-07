import math
import random

from etl.derivados import chuva_dengue as cd
from etl.derivados import vulnerabilidade as vul


def test_posicao_relativa_com_empates():
    assert vul.posicao({"a": 1, "b": 2, "c": 2, "d": 9, "e": None}) == {"a": 0.0, "b": 0.5, "c": 0.5, "d": 1.0}


def test_indice_combina_estrutural_e_historico():
    bairros = {k: {"nome": k.title(), "populacao": 10_000, "distrito_codigo": 1} for k in ("A", "B", "C", "D", "E")}
    comunidades = [{"chave_bairro": "A", "populacao_2014": 8000, "indicadores": {"IND_ALAGAM": 9, "DENS_ESCOR": 2}},
                   {"chave_bairro": "B", "populacao_2014": 1000, "indicadores": {"IND_ALAGAM": 1}}]
    linhas = {l["chave"]: l for l in vul.calcular(bairros, comunidades, {"A": 5, "B": 1},
                                                  {"A": 300, "B": 50, "C": 10}, {1: 100})}
    a = linhas["A"]
    assert a["pct_pop_comunidades"] == 0.8 and a["risco_comunidades"] == 9 and a["posicao"] == 1 and a["classe"] == "alta"
    assert a["atendimentos_10k_por_dia_forte"] == 3.0                 # 300 atendimentos / 100 dias / 10 mil hab
    assert linhas["E"]["classe"] == "baixa"


def _series(defasagem_real, semanas=520):
    random.seed(1)
    ses = [(2014 + i // 52) * 100 + i % 52 + 1 for i in range(semanas)]
    sazonal = [20 + 15 * math.sin(2 * math.pi * (i % 52) / 52) for i in range(semanas)]
    extra = [random.gauss(0, 10) for _ in range(semanas)]
    chuva = {se: max(0, sazonal[i] + extra[i]) for i, se in enumerate(ses)}
    dengue = {se: math.expm1(3 + 0.03 * sazonal[i] + 0.04 * (extra[i - defasagem_real] if i >= defasagem_real else 0)
                             + random.gauss(0, 0.05)) for i, se in enumerate(ses)}
    return chuva, dengue


def test_acha_a_defasagem_e_separa_da_sazonalidade():
    linhas = {l["defasagem_semanas"]: l for l in cd.calcular(*_series(defasagem_real=6))}
    melhor = max(linhas.values(), key=lambda l: l["corr_anomalia"] or -1)
    assert melhor["defasagem_semanas"] == 6 and melhor["corr_anomalia"] > 0.3
    assert abs(linhas[0]["corr_anomalia"]) < 0.15                    # sem defasagem, a anomalia não acompanha


import pytest  # noqa: E402


@pytest.mark.django_db
def test_api_da_vulnerabilidade(client, destino, monkeypatch):
    from apps.fontes.repositorios import conexao
    destino.banco["silver_bairros"].insert_one({"chave": "IBURA", "nome": "Ibura", "geometria": {"type": "Point", "coordinates": [0, 0]}})
    destino.banco["gold_vulnerabilidade_bairro"].insert_one({"chave": "IBURA", "indice": 0.9, "posicao": 1})
    monkeypatch.setattr(conexao, "banco", lambda: destino.banco)
    f = client.get("/api/vulnerabilidade/").json()["features"][0]
    assert f["properties"]["nome"] == "Ibura" and f["properties"]["posicao"] == 1
