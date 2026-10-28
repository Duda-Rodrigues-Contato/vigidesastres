from etl.fontes import cnes
from etl.fontes.cnes import Cnes
from vigidesastre.src.repositorios import conexao, referencia


def _est(codigo, tipo, lat="-8.05", lon="-34.9"):
    return {"codigo_cnes": codigo, "nome_fantasia": f"Unidade {codigo}", "codigo_tipo_unidade": tipo,
            "latitude_estabelecimento_decimo_grau": lat, "longitude_estabelecimento_decimo_grau": lon}


CADASTRO = [_est(1, 2), _est(2, 73), _est(3, 39), _est(4, 5, lat=None)]  # 39 = laboratório


def _api(monkeypatch):
    def get_json(url, params):
        if url.endswith("tipounidades"):
            return {"tipos_unidade": [{"codigo_tipo_unidade": 2, "descricao_tipo_unidade": "UBS"},
                                      {"codigo_tipo_unidade": 73, "descricao_tipo_unidade": "UPA"}]}
        ini = params["offset"]
        return {"estabelecimentos": CADASTRO[ini:ini + 2]}      # páginas de 2 para exercitar a paginação
    monkeypatch.setattr(cnes, "get_json", get_json)
    monkeypatch.setattr(cnes, "TAMANHO_PAGINA", 2)


def test_bronze_completo_silver_so_resposta(destino, monkeypatch):
    _api(monkeypatch)
    assert Cnes(destino).executar()["status"] == "ok"
    banco = destino.banco
    assert banco["bronze_cnes"].count_documents({}) == 4               # cadastro inteiro
    docs = {d["codigo_cnes"]: d for d in banco["silver_unidades_saude"].find()}
    assert set(docs) == {1, 2, 4}                                      # laboratório fica de fora
    assert docs[2]["tipo"] == "UPA" and docs[2]["localizacao"]["coordinates"] == [-34.9, -8.05]
    assert docs[4]["localizacao"] is None


def test_repositorio_so_com_coordenada_e_filtro(destino, monkeypatch):
    _api(monkeypatch)
    Cnes(destino).executar()
    monkeypatch.setattr(conexao, "banco", lambda: destino.banco)
    assert referencia.total_unidades() == 2
    assert [u["nome"] for u in referencia.unidades_saude([73])] == ["Unidade 2"]
    assert "_id" not in referencia.unidades_saude()[0]
