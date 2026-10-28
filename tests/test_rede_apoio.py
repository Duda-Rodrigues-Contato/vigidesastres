from etl.fontes import rede_apoio
from etl.fontes.rede_apoio import RedeApoio
from vigidesastre.src.repositorios import conexao, referencia

TABELAS = {
    "abrigos": [
        {"NOME": "Abrigo A", "BAIRRO": "Ibura", "ENDERECO": "Rua X", "N": "10", "LATITUDE": "-8,12", "LONGITUDE": "-34,95"},
        {"NOME": "Abrigo B", "BAIRRO": "Ibura", "ENDERECO": "Rua Y", "N": "", "LATITUDE": "-34.93", "LONGITUDE": "-8.05"},  # trocadas
        {"NOME": "Abrigo C", "BAIRRO": "Longe", "ENDERECO": "Rua Z", "N": "", "LATITUDE": "-23.5", "LONGITUDE": "-46.6"},  # SP
        {"NOME": "Abrigo D", "BAIRRO": "Ibura", "ENDERECO": "Rua W", "N": "", "LATITUDE": "", "LONGITUDE": ""},
    ],
    "unidades educacionais": [
        {"_id": 1, "NOME_UNIDADE": "Escola E", "BAIRRO": "Boa Vista", "LOGRADOURO": "Av", "LAT": "-8.06", "LON": "-34.89", "SITUACAO": "ATIVA"},
    ],
}


def _portal(monkeypatch):
    def pacote(busca, trecho, filtro=None):
        if busca == "*:*":
            return None                                   # CRAS fora do ar: não derruba o resto
        return {"title": f"Dataset {busca}", "resources": [{"format": "CSV", "name": "2024", "url": busca}]}
    monkeypatch.setattr(rede_apoio, "dataset_por_titulo", pacote)
    monkeypatch.setattr(rede_apoio, "ler_recurso", lambda r: TABELAS[r["url"]])


def test_pontos_validos_e_correcoes(destino, monkeypatch):
    _portal(monkeypatch)
    assert RedeApoio(destino).executar()["status"] == "ok"
    docs = {d["nome"]: d for d in destino.banco["silver_rede_apoio"].find()}
    assert set(docs) == {"Abrigo A", "Abrigo B", "Escola E"}       # SP e sem coordenada ficam de fora
    assert docs["Abrigo A"]["localizacao"]["coordinates"] == [-34.95, -8.12]   # vírgula decimal
    assert docs["Abrigo A"]["endereco"] == "Rua X, 10"
    assert docs["Abrigo B"]["localizacao"]["coordinates"] == [-34.93, -8.05]   # lat/lon destrocadas
    assert docs["Escola E"]["tipo"] == "escola" and docs["Escola E"]["detalhe"] == {"SITUACAO": "ATIVA"}
    assert destino.banco["bronze_rede_apoio"].count_documents({"_tipo": "abrigo"}) == 4


def test_repositorio_filtra_por_tipo(destino, monkeypatch):
    _portal(monkeypatch)
    RedeApoio(destino).executar()
    RedeApoio(destino).executar()
    monkeypatch.setattr(conexao, "banco", lambda: destino.banco)
    assert len(referencia.rede_apoio()) == 3                       # recarga não duplica
    assert [p["nome"] for p in referencia.rede_apoio("escola")] == ["Escola E"]
