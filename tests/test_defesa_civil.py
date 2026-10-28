from etl.fontes import defesa_civil
from etl.fontes.defesa_civil import DefesaCivil
from dominio.defesa_civil import eh_reativo, grau_de_risco

CSV = (
    "Data;Bairro;Endereco;Solicitacao;Ocorrencia;Grau_de_Risco\n"
    "2024-04-03;Água Fria;Rua Secreta 1;Colocação de Lonas Plásticas;;R3\n"
    "2024-04-03;agua fria ;Rua Secreta 2;Monitoramento;;\n"
    "2024-04-03;Ibura;Rua Secreta 3;;Alagamentos;r3\n"
    "03/04/2024;Ibura;Rua Secreta 4;monitoramento;;R9\n"
    "lixo;Ibura;Rua Secreta 5;Vistoria;;\n"
).encode("utf-8")

PACOTE = {"resources": [{"name": "Atendimentos 2024", "format": "CSV", "url": "http://x/2024.csv"}]}


def _portal_falso(monkeypatch):
    monkeypatch.setattr(defesa_civil, "dataset_por_titulo", lambda *a: PACOTE)
    monkeypatch.setattr(defesa_civil, "get_bytes", lambda url, timeout=None: CSV)


def test_classificacao():
    assert eh_reativo("Colocação de Lonas Plásticas", "")
    assert eh_reativo("Vistoria Setor Alagado", None)
    assert eh_reativo("", "Deslizamentos de Barreiras")
    assert not eh_reativo("Monitoramento", "")
    assert not eh_reativo("", "")
    assert grau_de_risco(" r3") == "R3" and grau_de_risco("R9") is None


def test_agrega_por_bairro_e_dia_sem_endereco(destino, monkeypatch):
    _portal_falso(monkeypatch)
    assert DefesaCivil(destino, anos=[2024]).executar()["status"] == "ok"
    banco = destino.banco
    assert "bronze_defesa_civil" not in banco.list_collection_names()
    silver = {d["bairro"]: d for d in banco["silver_defesa_civil_bairro_dia"].find()}
    assert set(silver) == {"AGUA FRIA", "IBURA"}
    assert (silver["AGUA FRIA"]["reativos"], silver["AGUA FRIA"]["rotina"]) == (1, 1)
    assert (silver["IBURA"]["reativos"], silver["IBURA"]["rotina"]) == (1, 1)
    assert silver["IBURA"]["por_risco"] == {"R3": 1}
    for d in silver.values():
        assert "Endereco" not in d and "Rua Secreta" not in str(d)


def test_gold_soma_o_dia(destino, monkeypatch):
    _portal_falso(monkeypatch)
    DefesaCivil(destino, anos=[2024]).executar()
    g = destino.banco["gold_defesa_civil_dia_cidade"].find_one()
    assert (g["total"], g["reativos"], g["rotina"], g["bairros_com_reativo"]) == (4, 2, 2, 2)


def test_rodar_de_novo_nao_duplica(destino, monkeypatch):
    _portal_falso(monkeypatch)
    DefesaCivil(destino, anos=[2024]).executar()
    DefesaCivil(destino, anos=[2024]).executar()
    assert destino.banco["silver_defesa_civil_bairro_dia"].count_documents({}) == 2


# 2015/2019/2020/2022: valores deslocados uma coluna; "Solicitacao" traz o endereço
CSV_DESLOCADO = (
    "Regional;Ano;Mês;Data;Ocorrencia;Solicitacao;Endereco;Bairro;Grau_de_Risco\n"
    "2015;4;2015-04-30;;Monitoramento;Rua Secreta 9;x;Ibura;\n"
    "2015;4;2015-04-30;Alagamentos;Vistoria;Rua Secreta 8;x;Ibura;R2\n"
).encode("cp1252")


def test_layout_deslocado_le_data_certa_e_ignora_endereco(destino, monkeypatch):
    monkeypatch.setattr(defesa_civil, "dataset_por_titulo", lambda *a: PACOTE)
    monkeypatch.setattr(defesa_civil, "get_bytes", lambda url, timeout=None: CSV_DESLOCADO)
    DefesaCivil(destino, anos=[2024]).executar()
    d = destino.banco["silver_defesa_civil_bairro_dia"].find_one()
    assert d["data"].date().isoformat() == "2015-04-30"
    assert (d["total"], d["reativos"], d["rotina"]) == (2, 1, 1)
    assert set(d["por_tipo"]) == {"MONITORAMENTO", "VISTORIA"}
    assert "Rua Secreta" not in str(d)
