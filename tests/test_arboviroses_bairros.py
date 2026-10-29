from shapely.geometry import box, mapping

from etl.fontes import arboviroses_bairros as arbo
from etl.fontes import bairros as mod_bairros
from etl.fontes.arboviroses_bairros import ArbovirosesBairros, arquivos_de_casos, contar
from etl.fontes.bairros import Bairros
from vigidesastre.src.repositorios import arboviroses as repo_arbo
from vigidesastre.src.repositorios import conexao, referencia

POPULACAO = {"IBURA": {"nome": "Ibura", "cd_bairro_ibge": "1", "populacao": 10_000, "area_km2": 2.0},
             "RECIFE": {"nome": "Recife", "cd_bairro_ibge": "2", "populacao": 500, "area_km2": 1.0}}
CASOS = [
    {"CLASSI_FIN": 1, "NM_BAIRRO": "Ibura", "ID_MN_RESI": 261160},
    {"CLASSI_FIN": 5, "NM_BAIRRO": "IBURA ", "ID_MN_RESI": 261160},          # descartado
    {"CLASSI_FIN": 1, "NM_BAIRRO": "Bairro do Recife", "ID_MN_RESI": 261160},  # apelido
    {"CLASSI_FIN": 1, "NM_BAIRRO": "", "ID_MN_RESI": 261160},                # sem bairro
    {"CLASSI_FIN": 1, "NM_BAIRRO": "Inventado", "ID_MN_RESI": 261160},
    {"CLASSI_FIN": 1, "NM_BAIRRO": "Ibura", "ID_MN_RESI": 260790},           # Jaboatão
]
PACOTE = {"resources": [{"name": "Dengue 2024", "id": "d24", "datastore_active": True},
                        {"name": "Zika 2024", "id": "z24", "datastore_active": True},
                        {"name": "Dengue 2019", "id": "d19", "datastore_active": False, "url": "http://x/d19.csv"},
                        {"name": "Metadados dengue 2024", "id": "m"}]}
# formato antigo (até 2020), só em CSV, com coluna pessoal que não pode sair do arquivo
CSV_2019 = ("co_municipio_residencia;no_bairro_residencia;tp_classificacao_final;dt_nascimento\n"
            "2611606;IBURA;10;1990-01-01\n261160;Ibura;5;1991-01-01\n").encode("cp1252")


def test_arquivos_e_contagem():
    assert [a["id"] for a in arquivos_de_casos(PACOTE, [2024])] == ["d24", "z24"]
    assert arquivos_de_casos(PACOTE, [2019])[0]["api"] is False
    contagem, q = contar(CASOS, POPULACAO)
    assert contagem == {"IBURA": {"notificados": 2, "descartados": 1}, "RECIFE": {"notificados": 1, "descartados": 0}}
    assert (q["sem_bairro"], q["nao_reconhecidos"], q["fora_do_recife"]) == (1, 1, 1)


def _portal(monkeypatch):
    monkeypatch.setattr(arbo.ibge, "linhas_do_recife", lambda: [])
    monkeypatch.setattr(arbo.ibge, "populacao_por_bairro", lambda linhas: POPULACAO)
    monkeypatch.setattr(arbo, "dataset_por_titulo", lambda *a: PACOTE)
    monkeypatch.setattr(arbo, "campos_disponiveis", lambda rid: {"CLASSI_FIN", "NM_BAIRRO", "ID_MN_RESI", "DT_NASC"})
    monkeypatch.setattr(arbo, "get_bytes", lambda url, **k: CSV_2019)
    pedidos = []

    def ler(rid, campos):
        pedidos.append(campos)
        return CASOS if rid == "d24" else []
    monkeypatch.setattr(arbo, "ler_datastore", ler)
    return pedidos


def test_silver_sem_bronze_e_so_campos_necessarios(destino, monkeypatch):
    pedidos = _portal(monkeypatch)
    assert ArbovirosesBairros(destino, anos=[2024]).executar()["status"] == "ok"
    assert all("DT_NASC" not in c for c in pedidos)                         # LGPD: nunca pede o resto
    b = destino.banco
    assert "bronze_arboviroses_bairros" not in b.list_collection_names()
    ibura = b["silver_arboviroses_bairro_ano"].find_one({"doenca": "dengue", "chave": "IBURA"})
    assert (ibura["provaveis"], ibura["incidencia_10k"]) == (1, 1.0)
    assert b["silver_arboviroses_bairro_ano"].count_documents({"doenca": "zika"}) == 2   # bairros com zero
    ArbovirosesBairros(destino, anos=[2024]).executar()
    assert b["silver_arboviroses_bairro_ano"].count_documents({}) == 4                    # não duplica
    assert b["silver_qualidade_arboviroses"].count_documents({}) == 2


def test_formato_antigo_em_csv_sem_dado_pessoal(destino, monkeypatch):
    _portal(monkeypatch)
    ArbovirosesBairros(destino, anos=[2019]).executar()
    ibura = destino.banco["silver_arboviroses_bairro_ano"].find_one({"ano": 2019, "chave": "IBURA"})
    assert (ibura["notificados"], ibura["descartados"], ibura["provaveis"]) == (2, 1, 1)
    assert "1990" not in str(list(destino.banco["silver_qualidade_arboviroses"].find()))


def test_resolver_colunas_ignora_caixa():
    assert arbo.resolver_colunas(["id_mn_resi", "nm_bairro", "classi_fin", "x"]) == {
        "CLASSI_FIN": "classi_fin", "NM_BAIRRO": "nm_bairro", "ID_MN_RESI": "id_mn_resi"}


def test_bairros_e_repositorios(destino, monkeypatch):
    _portal(monkeypatch)
    monkeypatch.setattr(mod_bairros.ibge, "linhas_do_recife", lambda: [{"x": 1}])
    monkeypatch.setattr(mod_bairros.ibge, "populacao_por_bairro", lambda linhas: POPULACAO)
    monkeypatch.setattr(mod_bairros, "baixar_bairros", lambda: [
        {"properties": {"NOME": "IBURA", "Nome": "Ibura"}, "geometry": mapping(box(-34.95, -8.15, -34.93, -8.13))},
        {"properties": {"NOME": "RECIFE", "Nome": "Bairro do Recife"}, "geometry": mapping(box(-34.88, -8.07, -34.87, -8.06))}])
    Bairros(destino).executar()
    ArbovirosesBairros(destino, anos=[2024]).executar()
    monkeypatch.setattr(conexao, "banco", lambda: destino.banco)
    assert {b["chave"] for b in referencia.bairros()} == {"IBURA", "RECIFE"}
    assert repo_arbo.anos_por_bairro() == [2024]
    linhas = repo_arbo.por_bairro(2024, ["dengue", "zika"])
    assert {(l["chave"], l["doenca"]) for l in linhas} == {("IBURA", "dengue"), ("RECIFE", "dengue"),
                                                           ("IBURA", "zika"), ("RECIFE", "zika")}
def test_arquivo_trocado_no_portal():
    from dominio.arboviroses import doenca_pela_classificacao
    assert doenca_pela_classificacao("zika", {"5": 1800, "13": 15864}) == "chikungunya"
    assert doenca_pela_classificacao("chikungunya", {"5": 1800, "13": 15864}) is None
    assert doenca_pela_classificacao("zika", {"2": 215, "1": 1}) is None
