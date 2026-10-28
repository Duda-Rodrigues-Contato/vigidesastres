from datetime import datetime, timedelta, timezone

from shapely.geometry import box

from etl.comum.cemaden import ler_serie
from etl.fontes import cemaden
from etl.fontes.cemaden import Cemaden, _hora_fechada

AGORA = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
H = AGORA - timedelta(hours=3)


def _csv(cod, lat, lon, leituras):
    cab = "OBS.: PCD com horario UTC!\ncod.estacao;nome;municipio;uf;latitude;longitude;datahora;sensor;valor;qualificacao;offset"
    corpo = [f"{cod};X;RECIFE;PE;{lat};{lon};{dt:%Y-%m-%d %H:%M:%S};chuva;{v};0000;" for dt, v in leituras]
    return "\n".join([cab, *corpo])


class ClienteFalso:
    """Distrito 1 com 2 estações, distrito 2 sem nenhuma; estação C inativa."""
    def estacoes_do_municipio(self, codibge, uf):
        return [{"codestacao": c, "id_tipoestacao": 1, "nome": c} for c in ("A", "B", "C")]

    def serie_csv(self, codigo, uf, inicio, fim):
        return {
            "A": _csv("A", -8.05, -34.95, [(H + timedelta(minutes=10), 2.0), (H + timedelta(minutes=20), 1.0),
                                           (AGORA + timedelta(hours=5), 9.9)]),   # futuro: descarta
            "B": _csv("B", -8.05, -34.92, [(H + timedelta(minutes=30), 6.0)]),
            "C": "",
        }[codigo]


def _rodar(destino, monkeypatch):
    monkeypatch.setattr(cemaden, "distritos_poligonos",
                        lambda: {1: box(-34.99, -8.10, -34.90, -8.00), 2: box(-34.90, -8.10, -34.80, -8.00)})
    return Cemaden(destino, cliente=ClienteFalso()).executar()


def test_ler_serie_pula_aviso():
    linhas = ler_serie(_csv("A", -8, -34, [(H, 1.5)]))
    assert len(linhas) == 1 and linhas[0]["valor"] == "1.5"
    assert ler_serie("Nenhum resultado foi encontrado") == []


def test_hora_fechada():
    assert _hora_fechada(H + timedelta(minutes=10)) == H + timedelta(hours=1)
    assert _hora_fechada(H) == H


def test_silver_e_gold(destino, monkeypatch):
    assert _rodar(destino, monkeypatch)["status"] == "ok"
    b = destino.banco
    assert b["silver_chuva_leituras"].count_documents({}) == 3              # a do futuro saiu
    est = {e["codestacao"]: e for e in b["silver_chuva_estacoes"].find()}
    assert est["A"]["distrito_codigo"] == 1 and est["B"]["distrito_codigo"] == 1
    assert est["C"]["ativa"] is False
    g1 = b["gold_chuva_distrito_hora"].find_one({"distrito_codigo": 1})
    assert (g1["chuva_media_mm"], g1["chuva_max_mm"], g1["estacao_max"]) == (4.5, 6.0, "B")
    g2 = b["gold_chuva_distrito_hora"].find_one({"distrito_codigo": 2})
    assert g2["estacao_proxima"] is True and g2["estacoes_com_dado"] == 1   # herdou a mais próxima
    assert b["bronze_cemaden"].count_documents({}) == 2                       # C sem CSV não vai


def test_rodar_de_novo_nao_duplica(destino, monkeypatch):
    _rodar(destino, monkeypatch)
    _rodar(destino, monkeypatch)
    assert destino.banco["silver_chuva_leituras"].count_documents({}) == 3
    assert destino.banco["gold_chuva_distrito_hora"].count_documents({}) == 2
