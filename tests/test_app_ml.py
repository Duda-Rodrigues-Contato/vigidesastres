from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from ml import demanda, painel
from tests.test_demanda import GRADE, _diario

st_testing = pytest.importorskip("streamlit.testing.v1")


@pytest.fixture
def painel_falso(monkeypatch):
    diario = _diario()
    s = demanda.semanal(diario)
    detalhes = {}
    demanda.executar(s, GRADE, avisar=lambda t: None, detalhes=detalhes)
    pacote = demanda.treinar_final(s[s["ano"] <= 2023], GRADE)
    gravado = []

    def ler_diario(desde=None, ate=None):
        d = diario.copy()
        d["data"] = pd.to_datetime(d["data"])
        if desde:
            d = d[(d["data"] >= desde) & (d["data"] < ate)]
        return d

    monkeypatch.setattr(painel, "ler_diario", ler_diario)
    monkeypatch.setattr(painel, "ler_avaliacao", lambda: detalhes)
    monkeypatch.setattr(painel, "ler_pacote", lambda: pacote)
    monkeypatch.setattr(painel, "gravar_simulacao", lambda docs: gravado.extend(docs))
    monkeypatch.setattr(painel, "ler_tabela", lambda nome: pd.DataFrame(gravado))
    return detalhes, gravado


def test_painel_abre_e_simula(painel_falso):
    detalhes, gravado = painel_falso
    assert {"tabela", "escolhida", "teste", "importancia"} <= detalhes.keys()
    at = st_testing.AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app_ml.py"), default_timeout=120).run()
    assert not at.exception
    rotulos = [m.label for m in at.metric]
    assert "Distrito-semanas" in rotulos and "Erro (WAPE) no teste" in rotulos and "Silhueta" in rotulos
    at.selectbox[1].set_value(7)
    at.checkbox[0].check()
    at.button[0].click().run()
    assert not at.exception
    assert len(gravado) == 2 and all(d["real"] is not None for d in gravado)   # 2024: real conhecido
    assert any("gravada" in i.value for i in at.info)


def test_simular_semana_futura_sem_real(painel_falso):
    docs = painel.simular(date(2026, 11, 19), painel.ler_pacote())
    assert docs and all(d["real"] is None and not d["completa"] for d in docs)
