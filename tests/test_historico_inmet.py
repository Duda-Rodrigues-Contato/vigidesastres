import io
import zipfile

from etl.historico import inmet

CAB = ("REGIAO:;NE\nUF:;PE\nESTACAO:;RECIFE\nCODIGO (WMO):;A301\nLATITUDE:;-8,05\nLONGITUDE:;-34,95\n"
       "ALTITUDE:;10,00\nDATA DE FUNDACAO:;2004-05-14\n")


def _zip(formato):
    if formato == "antigo":
        linhas = ("DATA (YYYY-MM-DD);HORA (UTC);PRECIPITAÇÃO TOTAL, HORÁRIO (mm);TEMPERATURA\n"
                  "2014-01-01;1500;2,5;29\n2014-01-01;1600;-9999;29\n2014-01-02;0200;4,0;25\n")
    else:
        linhas = ("Data;Hora UTC;PRECIPITAÇÃO TOTAL, HORÁRIO (mm);TEMPERATURA;\n"
                  "2024/01/01;1500 UTC;2,5;29;\n2024/01/01;1600 UTC;;29;\n2024/01/02;0200 UTC;4,0;25;\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("INMET_NE_PE_A301_RECIFE_01-01-X.CSV", (CAB + linhas).encode("latin-1"))
        z.writestr("INMET_NE_PE_A307_PETROLINA_01-01-X.CSV", b"outra estacao")
    return buf.getvalue()


def test_os_dois_formatos_de_csv():
    for formato in ("antigo", "novo"):
        dias = inmet.por_dia(inmet.csv_da_estacao(_zip(formato)), None)
        assert len(dias) == 1                                   # 02:00 UTC do dia 2 é 23:00 do dia 1 no Recife
        assert (dias[0]["chuva_mm"], dias[0]["max_hora_mm"], dias[0]["horas_com_dado"]) == (6.5, 4.0, 2)


def test_retoma_por_ano(destino):
    baixados = []
    baixar = lambda ano: baixados.append(ano) or _zip("novo")
    inmet.carregar(destino, 2023, 2024, baixar=baixar, avisar=lambda s: None)
    inmet.carregar(destino, 2023, 2024, baixar=baixar, avisar=lambda s: None)
    assert baixados == [2023, 2024]                             # a segunda rodada não baixa de novo
    assert destino.banco["silver_chuva_inmet_dia"].count_documents({}) == 1


def test_noite_do_ano_anterior_nao_apaga_o_31_de_dezembro(destino):
    def pacote(ano):
        linhas = ("Data;Hora UTC;PRECIPITAÇÃO TOTAL, HORÁRIO (mm);\n"
                  + ("2019/12/31;1200 UTC;10,0;\n" if ano == 2019 else "2020/01/01;0100 UTC;1,0;\n2020/01/01;1200 UTC;2,0;\n"))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("INMET_NE_PE_A301_RECIFE.CSV", (CAB + linhas).encode("latin-1"))
        return buf.getvalue()
    inmet.carregar(destino, 2019, 2020, baixar=pacote, avisar=lambda s: None)
    dias = {d["data"].strftime("%Y-%m-%d"): d["chuva_mm"] for d in destino.banco["silver_chuva_inmet_dia"].find()}
    assert dias == {"2019-12-31": 10.0, "2020-01-01": 2.0}   # 01:00 UTC de 01/01 (22h local de 31/12) não sobrescreve
