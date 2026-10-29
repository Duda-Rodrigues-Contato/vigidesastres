"""População por bairro do Recife, Censo 2022 (IBGE, agregados por bairro).

O arquivo do IBGE traz o Brasil inteiro; aqui fica só o Recife. A soma é
conferida contra a população oficial do município: se não bater, a coluna
mudou de sentido e é melhor parar do que gravar número errado.
"""

import csv
import io
import zipfile

from etl.comum.http import get_bytes
from etl.comum.texto import normalizar

URL = ("https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/"
       "Agregados_por_Bairro_csv/Agregados_por_bairros_basico_BR_20260520.zip")
COD_RECIFE = "2611606"
POPULACAO_RECIFE_2022 = 1_488_920
FONTE = "IBGE, Censo 2022"


def linhas_do_recife():
    """As linhas do CSV do IBGE que são do Recife, como vieram (dado público, agregado)."""
    zip_ = zipfile.ZipFile(io.BytesIO(get_bytes(URL, timeout=300)))
    nome = next(n for n in zip_.namelist() if n.lower().endswith(".csv"))
    leitor = csv.DictReader(io.StringIO(zip_.read(nome).decode("latin-1")), delimiter=";")
    return [l for l in leitor if l["CD_MUN"] == COD_RECIFE]


def populacao_por_bairro(linhas):
    """{chave normalizada: {nome, cd_bairro_ibge, populacao, area_km2}}, conferida."""
    bairros = {normalizar(l["NM_BAIRRO"]): {
        "nome": l["NM_BAIRRO"],
        "cd_bairro_ibge": l["CD_BAIRRO"],
        "populacao": int(l["v0001"]),
        "area_km2": float(l["AREA_KM2"].replace(",", ".")),
    } for l in linhas}
    total = sum(b["populacao"] for b in bairros.values())
    if abs(total - POPULACAO_RECIFE_2022) > POPULACAO_RECIFE_2022 * 0.01:
        raise ValueError(f"a soma por bairro ({total}) não bate com a população do Recife "
                         f"({POPULACAO_RECIFE_2022}): a coluna v0001 pode ter mudado de sentido")
    return bairros
