from datetime import date, datetime, timedelta, timezone

import pytest

from apps.painel import graficos


def test_g3_normal_com_janela_e_razao():
    historico = [(date(2020, 11, d), 10.0) for d in range(1, 31)] + [(date(2021, 11, 15), 30.0)]
    normal = graficos.normal_por_dia_do_ano(historico)
    assert normal[(11, 15)] > normal[(11, 5)] and (2, 29) in normal
    hoje = date(2026, 11, 27)
    recente = {"rotulos": [str(i) for i in range(30)],
               "series": [{"tipo": "bar", "valores": [0] * 30}, {"tipo": "line", "valores": [20.0] * 30}]}
    g = graficos.chuva_30_dias(recente, normal, hoje)
    assert len(g["normal"]) == 30 and g["razao"] > 1


def test_g4_sazonalidade_e_ponto_da_previsao():
    semanais = [(2020, 21, 400), (2021, 21, 600), (2020, 47, 100)]
    prev = [{"previsto": 50.4, "inicio_semana": "2024-05-20", "completa": True},
            {"previsto": 49.8, "inicio_semana": "2024-05-20", "completa": True}]
    g = graficos.sazonalidade_atendimentos(semanais, prev, date(2026, 11, 27))
    assert g["media"][20] == 500 and g["minimo"][20] == 400 and g["maximo"][20] == 600
    assert g["semana_atual"] == 21 and g["previsto"] == 100 and g["completa"]


def test_g5_ano_contra_ano_anterior():
    docs = [{"ano": 2025, "semana": 1, "estimados": 80}, {"ano": 2026, "semana": 1, "estimados": 60, "nivel": 2},
            {"ano": 2026, "semana": 2, "estimados": 65}]
    g = graficos.arboviroses_ano_a_ano(docs)
    assert g["ano"] == 2026 and g["atual"][:3] == [60, 65, None] and g["anterior"][0] == 80 and g["ultima_semana"] == 2


def test_g7_conta_por_dia_e_nivel():
    hoje = date(2026, 11, 27)
    al = [{"nivel": "ALTO", "criado_em": datetime(2026, 11, 27, 10, tzinfo=timezone.utc)},
          {"nivel": "MÉDIO", "criado_em": datetime(2026, 11, 27, 11, tzinfo=timezone.utc)},
          {"nivel": "ALTO", "criado_em": datetime(2026, 11, 20, tzinfo=timezone.utc)}]
    g = graficos.alertas_30_dias(al, 2, hoje)
    assert g["alto"][-1] == 1 and g["medio"][-1] == 1 and g["alto"][-8] == 1 and g["total"] == 3 and g["sem_acao"] == 2


def test_g8_demanda_e_real_so_quando_existe():
    docs = [{"distrito_codigo": 2, "distrito": "DS II", "previsto": 90, "normal": 80, "inicio_semana": "a", "fim_semana": "b"},
            {"distrito_codigo": 1, "distrito": "DS I", "previsto": 20, "normal": 25, "inicio_semana": "a", "fim_semana": "b"}]
    g = graficos.demanda_por_distrito(docs)
    assert g["distritos"] == ["DS I", "DS II"] and g["real"] is None


def test_chuva_prevista_colore_pela_classe():
    g = graficos.chuva_prevista_distritos([{"distrito_codigo": 2, "distrito": "DS II", "chuva_prox_24h_mm": 60},
                                           {"distrito_codigo": 1, "distrito": "DS I", "chuva_prox_24h_mm": 1},
                                           {"distrito_codigo": 3, "distrito": "DS III", "chuva_prox_24h_mm": None}])
    assert g["distritos"] == ["DS I", "DS II"] and g["classes"] == ["Seco", "Chuva muito forte"]
    assert g["cores"][1] == "#dc2626" and graficos.chuva_prevista_distritos([]) is None


def test_calor_48h_em_hora_local():
    g = graficos.calor_48h([{"_id": datetime(2026, 11, 27, 18), "indice": 35.1, "temperatura": 31}])
    assert g["rotulos"] == ["27/11 15h"] and g["indice"] == [35.1] and g["perigo"] == 41
    assert graficos.calor_48h([]) is None


def test_indicadores_pegam_o_distrito_mais_quente():
    i = graficos.indicadores(None, 2, 0, None, [{"distrito": "DS I", "indice_calor_max_24h_c": 34, "temp_max_24h_c": 31},
                                                 {"distrito": "DS VI", "indice_calor_max_24h_c": 42, "temp_max_24h_c": 33}])
    assert i["calor_max"] == 42 and i["calor_faixa"] == "Perigo" and i["calor_distrito"] == "DS VI"


@pytest.mark.django_db
def test_dashboard_abre_so_com_dados_atuais(client, monkeypatch):
    monkeypatch.setattr(graficos, "todos", lambda: {
        "indicadores": graficos.indicadores({"chuva_24h": 12.5}, 3, 1, None,
                                            [{"distrito": "DS VI", "indice_calor_max_24h_c": 36, "temp_max_24h_c": 32}]),
        "calor": graficos.calor_48h([{"_id": datetime(2026, 11, 27, 18), "indice": 35.1, "temperatura": 31}]),
        "chuva_prevista": None, "chuva_30": None, "arbo": None, "alertas": graficos.alertas_30_dias([], 1, date.today())})
    html = client.get("/dashboard/").content.decode()
    for trecho in ["Calor nas próximas 48 h", "Cautela extrema · DS VI", 'id="d-calor"', "1 sem ação registrada"]:
        assert trecho in html, trecho
    assert "maré" not in html.lower() and "Demanda prevista" not in html


@pytest.mark.django_db
def test_calendario_mostra_os_graficos_de_demanda(client, monkeypatch):
    from apps.painel import views
    monkeypatch.setattr(views, "_demanda_da_semana", lambda: {"distritos": [], "inicio": "23/11/2026", "fim": "29/11/2026",
                                                              "completa": True, "dados_ate": "x", "demonstracao": False})
    monkeypatch.setattr(graficos, "demanda_calendario", lambda: {
        "sazonalidade": graficos.sazonalidade_atendimentos([(2020, 21, 400)], [], date(2026, 11, 27)),
        "por_distrito": graficos.demanda_por_distrito([{"distrito_codigo": 1, "distrito": "DS I", "previsto": 20,
                                                        "normal": 25, "inicio_semana": "2026-11-23", "fim_semana": "2026-11-29"}])})
    from apps.fontes.repositorios import calendario as repo_cal
    monkeypatch.setattr(repo_cal, "por_mes", lambda: [{"distrito_codigo": 1, "distrito": "DS I", "mes": 5, "indice": 1.7,
        "media_dia": 3, "ano_calmo": 2015, "media_ano_calmo": 1, "ano_intenso": 2022, "media_ano_intenso": 6}])
    monkeypatch.setattr(repo_cal, "por_distrito", lambda: [])
    html = client.get("/calendario/").content.decode()
    assert 'id="d-demanda-distrito"' in html and 'id="d-demanda-ano"' in html and "painel/calendario.js" in html
