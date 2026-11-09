from datetime import datetime

from etl.historico import cemaden as hist

CAB = "OBS.: PCD com horario UTC!\ncod.estacao;nome;municipio;uf;latitude;longitude;datahora;sensor;valor;qualificacao;offset"


def _csv(linhas):
    return "\n".join([CAB, *[f"A;X;RECIFE;PE;-8;-34.9;{dt};chuva;{v};0000;" for dt, v in linhas]])


class Cliente:
    def __init__(self):
        self.pedidos = []

    def estacoes_do_municipio(self, codibge, uf):
        return [{"codestacao": "A"}, {"codestacao": "B"}]

    def serie_csv(self, codigo, uf, inicio, fim):
        self.pedidos.append((codigo, inicio.strftime("%Y-%m")))
        if codigo == "B":
            return ""  # estação ainda não existia
        return _csv([("2014-01-01 12:10:00", 2.0), ("2014-01-01 12:50:00", 3.0), ("2014-01-01 15:00:00", 1.0),
                     ("2014-01-02 02:30:00", 4.0)])  # 23:30 do dia 1 no Recife


def test_dia_local_total_e_intensidade():
    linhas = {l["data"].day: l for l in hist.por_dia(_csv([("2014-01-01 12:10:00", 2.0), ("2014-01-01 12:50:00", 3.0),
                                                            ("2014-01-02 02:30:00", 4.0)]), "A", None)}
    assert (linhas[1]["chuva_mm"], linhas[1]["max_hora_mm"]) == (9.0, 5.0)   # 02:30 UTC ainda é dia 1 no Recife
    assert linhas[1]["hora_pico_utc"] == datetime(2014, 1, 1, 12)            # 12:10 e 12:50 caíram entre 12h e 13h
    assert 2 not in linhas


def test_carga_retoma_de_onde_parou(destino):
    c = Cliente()
    hist.carregar(destino, c, "2014-01", "2014-02", avisar=lambda s: None, espera=0)
    assert len(c.pedidos) == 4
    c2 = Cliente()
    hist.carregar(destino, c2, "2014-01", "2014-03", avisar=lambda s: None, espera=0)
    assert c2.pedidos == [("A", "2014-03"), ("B", "2014-03")]              # só o mês novo
    assert destino.banco["silver_chuva_estacao_dia"].count_documents({}) == 1   # upsert: não duplica


class ClienteInstavel(Cliente):
    """O servidor do CEMADEN às vezes devolve erro 500: aqui, sempre no mês de fevereiro."""
    def serie_csv(self, codigo, uf, inicio, fim):
        if inicio.month == 2:
            self.pedidos.append((codigo, inicio.strftime("%Y-%m")))
            raise hist.requests.HTTPError("500")
        return super().serie_csv(codigo, uf, inicio, fim)


def test_mes_com_erro_nao_derruba_a_carga_e_volta_na_proxima(destino):
    c = ClienteInstavel()
    hist.carregar(destino, c, "2014-01", "2014-02", avisar=lambda s: None, espera=0)
    falhas = destino.banco["controle_historico"].count_documents({"status": "falha"})
    assert falhas == 2 and c.pedidos.count(("A", "2014-02")) == hist.TENTATIVAS
    c2 = Cliente()
    hist.carregar(destino, c2, "2014-01", "2014-02", avisar=lambda s: None, espera=0)
    assert c2.pedidos == [("A", "2014-02"), ("B", "2014-02")]   # só os que falharam


def test_janela_e_o_mes_local():
    from datetime import datetime, timezone
    ini, fim = hist.janela_do_mes(2014, 12)
    assert ini == datetime(2014, 12, 1, 3, 1, tzinfo=timezone.utc)
    assert fim == datetime(2015, 1, 1, 3, 0, tzinfo=timezone.utc)   # a leitura das 00:00 local de 01/01 é do dia 31


def test_leitura_da_meia_noite_nao_sobrescreve_o_mes_anterior(destino):
    class Cliente2(Cliente):
        def estacoes_do_municipio(self, codibge, uf):
            return [{"codestacao": "A"}]

        def serie_csv(self, codigo, uf, inicio, fim):
            if inicio.month == 1:   # janeiro: chuva no dia 31 às 20h local, e a leitura da meia-noite de 01/02
                return _csv([("2014-01-31 23:00:00", 8.0), ("2014-02-01 03:00:00", 1.0)])
            return _csv([("2014-02-01 03:00:00", 1.0), ("2014-02-02 15:00:00", 2.0)])  # a API repete a borda
    hist.carregar(destino, Cliente2(), "2014-01", "2014-02", avisar=lambda s: None, espera=0)
    dias = {d["data"].strftime("%m-%d"): d["chuva_mm"] for d in destino.banco["silver_chuva_estacao_dia"].find()}
    assert dias == {"01-31": 9.0, "02-02": 2.0}


def test_refazer_baixa_de_novo_e_tem_controle_proprio(destino):
    c = Cliente()
    hist.carregar(destino, c, "2014-01", "2014-01", avisar=lambda s: None, espera=0)
    c2 = Cliente()
    hist.carregar(destino, c2, "2014-01", "2014-01", avisar=lambda s: None, espera=0, refazer=True)
    assert len(c2.pedidos) == 2                                    # baixou de novo
    c3 = Cliente()
    hist.carregar(destino, c3, "2014-01", "2014-01", avisar=lambda s: None, espera=0, refazer=True)
    assert c3.pedidos == []                                        # e a refeita também retoma
