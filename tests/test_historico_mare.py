from datetime import date

import numpy as np
import pytest

from etl.historico import mare

pytest.importorskip("utide")


def _serie_sintetica():
    """92 dias de uma maré com M2 de 0,8 m e S2 de 0,3 m: a soma vai de ~0,5 m (quadratura) a ~1,1 m (sizígia)."""
    tempos = np.arange(np.datetime64("2026-08-01T00"), np.datetime64("2026-11-01T00"), np.timedelta64(1, "h"))
    h = np.arange(len(tempos))
    return tempos, 0.8 * np.cos(2 * np.pi * h / 12.4206) + 0.3 * np.cos(2 * np.pi * h / 12.0)


def test_ajuste_recupera_as_componentes():
    coef, erro = mare.ajustar(*_serie_sintetica())
    amp = dict(zip(coef.name, coef.A))
    assert abs(amp["M2"] - 0.8) < 0.05 and abs(amp["S2"] - 0.3) < 0.05 and erro < 0.05


def test_historico_diario_tem_sizigia_e_quadratura(destino):
    mare.carregar(destino, date(2014, 1, 1), date(2014, 1, 31), serie=_serie_sintetica, avisar=lambda s: None)
    dias = list(destino.banco["silver_mare_calculada_dia"].find())
    assert len(dias) == 31
    maximos = [d["mare_max_m"] for d in dias]
    assert max(maximos) > 1.0 and min(maximos) < 0.7      # o ciclo de ~15 dias aparece no histórico
    assert destino.banco["silver_mare_calculada_hora"].count_documents({}) == 31 * 24


def test_serie_curta_demais_e_recusada(destino):
    curta = lambda: (_serie_sintetica()[0][:200], _serie_sintetica()[1][:200])
    with pytest.raises(ValueError):
        mare.carregar(destino, date(2014, 1, 1), date(2014, 1, 2), serie=curta, avisar=lambda s: None)
