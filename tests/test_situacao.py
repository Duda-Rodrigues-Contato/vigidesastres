import pytest

from apps.alertas.models import Alerta
from apps.painel import situacao

pytestmark = pytest.mark.django_db


@pytest.fixture
def fontes(monkeypatch):
    monkeypatch.setattr(situacao.painel_chuva, "distritos_para_gatilhos", lambda: [
        {"nome": "DS I", "codigo": 1, "chuva_prox_24h_mm": 80.0, "chuva_72h_mm": 10.0},
        {"nome": "DS II", "codigo": 2, "chuva_prox_24h_mm": 1.0, "chuva_72h_mm": 0.0},
    ])
    monkeypatch.setattr(situacao, "resumo_mare", lambda: None)
    monkeypatch.setattr(situacao.limiares, "avaliar_gatilhos", lambda d, m: [
        {"tipo": "Deslizamento", "nivel": "ALTO", "zona": "DS I", "motivo": "Previsão de 80 mm"}])
    monkeypatch.setattr(situacao.repo_chuva, "ultima_leitura", lambda: None)


def test_nivel_vem_dos_gatilhos_e_falta_de_dado_nao_e_normal(fontes):
    s = {d["nome"]: d for d in situacao.situacao_por_distrito()}
    assert len(s) == 8
    assert s["DS I"]["nivel"] == "ALTO" and s["DS I"]["motivos"] == ["Previsão de 80 mm"]
    assert s["DS II"]["nivel"] == "NORMAL"
    assert s["DS V"]["nivel"] == "SEM DADO"


def test_conta_so_alertas_nao_encerrados(fontes):
    for status in ("aberto", "monitorando", "encerrado"):
        Alerta.objects.create(titulo="x", tipo="x", nivel="ALTO", distrito="DS I", motivo="x",
                              chave=status, status=status)
    assert {d["nome"]: d for d in situacao.situacao_por_distrito()}["DS I"]["alertas_abertos"] == 2


def test_api_do_mapa(client, fontes):
    r = client.get("/api/situacao-distritos/")
    assert r.status_code == 200 and r.json()["distritos"][0]["nivel"] == "ALTO"


def _d(nome, nivel, motivo=None):
    return {"nome": nome, "nivel": nivel, "motivos": [motivo] if motivo else []}


def test_faixa_prioriza_o_pior_caso():
    assert situacao.resumo_geral([_d("DS I", "ALTO", "80 mm"), _d("DS II", "MÉDIO", "x")], [])["estado"] == "ALERTA"
    assert situacao.resumo_geral([_d("DS I", "NORMAL")], [{"evento": "Chuva", "severidade": "Perigo"}])["estado"] == "ATENÇÃO"
    assert situacao.resumo_geral([_d("DS I", "SEM DADO")], [])["estado"] == "SEM DADOS"
    normal = situacao.resumo_geral([_d("DS I", "NORMAL"), _d("DS II", "SEM DADO")], [])
    assert normal["estado"] == "NORMAL" and "DS II" in normal["frase"]


def test_tons_das_celulas():
    assert [situacao.tom_chuva(v) for v in (None, 2, 10, 30, 60)] == ["", "", "amarelo", "laranja", "vermelho"]
    assert [situacao.tom_acumulado(v) for v in (10, 40, 70)] == ["", "laranja", "vermelho"]


def test_planilha(client, fontes):
    r = client.get("/dashboard/situacao.csv")
    linhas = r.content.decode("utf-8-sig").splitlines()
    assert r.status_code == 200 and linhas[0].startswith("Distrito;Situação") and len(linhas) == 9
