from etl.fontes import areas_risco
from etl.fontes.areas_risco import AreasRisco
from vigidesastre.src.repositorios import conexao, referencia


def _quadrado(x):
    return {"type": "Polygon", "coordinates": [[[x, -8], [x + .01, -8], [x + .01, -8.01], [x, -8.01], [x, -8]]]}


BAIRROS = [
    {"properties": {"NOME": "IBURA", "Nome": "Ibura"}, "geometry": _quadrado(-34.90)},
    {"properties": {"NOME": "CORDEIRO", "Nome": "Cordeiro"}, "geometry": _quadrado(-34.92)},
    {"properties": {"NOME": "MADALENA", "Nome": "Madalena"}, "geometry": _quadrado(-34.94)},
]
PLANILHA = [
    {"tipo": "deslizamento", "regional": "Sul", "localidade": "Grota A", "bairro": "Ibura de Baixo"},
    {"tipo": "alagamento", "regional": "Sul", "localidade": "Rua B", "bairro": "Ibura"},
    {"tipo": "alagamento", "regional": "Oeste", "localidade": "Canal C", "bairro": "Cordeiro / Madalena"},
    {"tipo": "alagamento", "regional": "Oeste", "localidade": "X", "bairro": "Bairro Inventado"},
]


def _fontes(monkeypatch):
    monkeypatch.setattr(areas_risco, "ler_planilha", lambda: PLANILHA)
    monkeypatch.setattr(areas_risco, "baixar_bairros", lambda: BAIRROS)


def test_agrupa_por_bairro_com_apelidos(destino, monkeypatch):
    _fontes(monkeypatch)
    assert AreasRisco(destino).executar()["status"] == "ok"
    docs = {d["chave"]: d for d in destino.banco["silver_areas_risco"].find()}
    assert set(docs) == {"IBURA", "CORDEIRO", "MADALENA"}         # inventado fica de fora
    ibura = docs["IBURA"]
    assert ibura["bairro"] == "Ibura"                             # grafia normal, não maiúscula
    assert ibura["tipos"] == ["alagamento", "deslizamento"] and ibura["total_areas"] == 2
    assert ibura["deslizamento"] == ["Grota A (Ibura de Baixo)"]  # mostra o nome do plano
    assert docs["MADALENA"]["alagamento"] == ["Canal C (Cordeiro / Madalena)"]
    assert destino.banco["bronze_areas_risco"].count_documents({}) == 4


def test_recarga_substitui(destino, monkeypatch):
    _fontes(monkeypatch)
    AreasRisco(destino).executar()
    AreasRisco(destino).executar()
    assert destino.banco["silver_areas_risco"].count_documents({}) == 3


def test_repositorio(destino, monkeypatch):
    _fontes(monkeypatch)
    AreasRisco(destino).executar()
    monkeypatch.setattr(conexao, "banco", lambda: destino.banco)
    a = referencia.areas_risco()
    assert len(a) == 3 and "_id" not in a[0]
