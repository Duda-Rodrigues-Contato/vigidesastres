from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError

from apps.alertas import servicos
from apps.alertas.models import AcaoResposta, Alerta

pytestmark = pytest.mark.django_db

GATILHO = {"tipo": "Deslizamento", "nivel": "ALTO", "zona": "DS III", "motivo": "Previsão de 80 mm em 24h"}
AVISO = {"id": "123", "evento": "Acumulado de Chuva", "nivel": 2, "severidade": "Perigo", "descricao": "Chuva de 50 mm"}


def _fontes(monkeypatch, gatilhos):
    monkeypatch.setattr(servicos.painel_chuva, "distritos_para_gatilhos", lambda: [{"nome": "DS III"}])
    monkeypatch.setattr(servicos, "resumo_mare", lambda: None)
    monkeypatch.setattr(servicos.limiares, "avaliar_gatilhos", lambda d, m: gatilhos)
    monkeypatch.setattr(servicos.painel_chuva, "avisos_oficiais", lambda: [AVISO])


def test_gera_e_nao_duplica(monkeypatch):
    _fontes(monkeypatch, [GATILHO])
    assert servicos.gerar_alertas() == {"novos": 2, "atualizados": 0}
    assert servicos.gerar_alertas() == {"novos": 0, "atualizados": 2}
    assert Alerta.objects.count() == 2
    inmet = Alerta.objects.get(origem="inmet")
    assert (inmet.nivel, inmet.distrito) == ("MÉDIO", "Recife")


def test_status_da_equipe_nao_e_sobrescrito(monkeypatch):
    _fontes(monkeypatch, [GATILHO])
    servicos.gerar_alertas()
    a = Alerta.objects.get(origem="gatilho")
    a.status = Alerta.Status.ENCERRADO
    a.save()
    servicos.gerar_alertas()
    a.refresh_from_db()
    assert a.status == "encerrado"


def test_acao_concluida_nao_aceita_data_futura():
    acao = AcaoResposta(nome="Vistoria", distrito="DS V", data=date.today() + timedelta(days=1), status="concluida")
    with pytest.raises(ValidationError):
        acao.full_clean()


def test_api_cria_acao_e_rejeita_data_futura(client):
    ok = client.post("/api/acoes/", {"name": "Vistoria", "team": "", "district": "DS V",
                                      "date": date.today().isoformat(), "status": "Concluída"},
                     content_type="application/json")
    assert ok.status_code == 201 and ok.json()["team"] == "Equipe designada"
    ruim = client.post("/api/acoes/", {"name": "X", "district": "DS V",
                                        "date": (date.today() + timedelta(days=2)).isoformat(), "status": "Concluída"},
                       content_type="application/json")
    assert ruim.status_code == 400 and "posterior a hoje" in ruim.json()["erro"]
    assert AcaoResposta.objects.count() == 1


def test_tela_de_alertas_mostra_do_banco_e_muda_status(client):
    a = Alerta.objects.create(titulo="Deslizamento — DS III", tipo="Deslizamento", nivel="ALTO",
                              distrito="DS III", motivo="teste", chave="x")
    tela = client.get("/alertas/")
    assert tela.status_code == 200 and "Deslizamento" in tela.content.decode() and tela.context["totais"]["aberto"] == 1
    r = client.post(f"/api/alertas/{a.id}/status/", {"status": "monitorando"}, content_type="application/json")
    assert r.status_code == 200 and r.json()["status"] == "Monitorando"
