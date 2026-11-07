from shapely.geometry import box

from etl.comum.distritos import distrito_de

POLIGONOS = {1: box(0, 0, 10, 10), 2: box(10, 0, 20, 10)}


def test_bairro_na_divisa_fica_no_maior_pedaco():
    assert distrito_de(box(7, 1, 12, 2), POLIGONOS) == 1   # 3 de área no 1, 2 no 2
    assert distrito_de(box(8, 1, 15, 2), POLIGONOS) == 2


def test_fora_de_todos_vai_para_o_mais_proximo():
    assert distrito_de(box(21, 1, 22, 2), POLIGONOS) == 2
