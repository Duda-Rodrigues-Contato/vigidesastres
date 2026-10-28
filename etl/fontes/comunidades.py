"""Comunidades de Interesse Social (CIS) do Recife, com indicadores de
infraestrutura e risco.

Fonte: Portal de Dados Abertos do Recife, "Relação das favelas, cortiços e
loteamentos irregulares" - 545 polígonos, levantamento de 2014.

  bronze  bronze_comunidades     uma Feature por documento, como veio
  silver  silver.comunidades     uma comunidade por documento

O cadastro é de 2014: retrato ESTRUTURAL (drenagem, encosta, saneamento
mudam devagar), não retrato atual de população. Os indicadores são notas de
0 a 10 sem dicionário publicado; a direção das escalas foi conferida contra
o Plano de Contingência 2024 em analises/comunidades/conferir_escalas.py.
"""

import json

from shapely.geometry import mapping, shape

from etl.base import Conector
from etl.comum.ckan import dataset_por_titulo, recurso_por_formato
from etl.comum.http import get_bytes
from etl.comum.texto import normalizar
from etl.destinos.base import Carga

# campos guardados (os nomes vêm truncados a 10 caracteres na origem)
INDICADORES = {
    "IND_ALAGAM": "alagamento",
    "DENS_ESCOR": "deslizamento",
    "DRENAGEM": "drenagem",
    "ABASTECIME": "abastecimento de água",
    "ESGOTAMENT": "esgotamento sanitário",
    "PAVIMENTAC": "pavimentação",
    "ILUMINACAO": "iluminação",
    "COLETA_LIX": "coleta de lixo",
    "DIST_SAUDE": "distância até saúde",
    "DIST_EDUC": "distância até educação",
    "Indice_COM": "índice composto",
}


def _numero(v):
    return v if isinstance(v, (int, float)) else None


def _texto(v):
    return (v or "").strip()


class Comunidades(Conector):
    nome = "comunidades"
    frequencia = "anual"
    descricao = "Comunidades de Interesse Social, levantamento de 2014 (portal do Recife)"

    def extrair(self):
        pacote = dataset_por_titulo("favelas", "favelas")
        if not pacote:
            raise ValueError("dataset das comunidades (favelas) não encontrado no portal")
        recurso = recurso_por_formato(pacote, "GEOJSON")
        return {"fonte": pacote["title"], "features": json.loads(get_bytes(recurso["url"], timeout=180))["features"]}

    def documentos_bronze(self, bruto):
        return bruto["features"]

    def transformar(self, bruto, coletado_em):
        docs = []
        for f in bruto["features"]:
            p = f["properties"]
            geometria = shape(f["geometry"])
            rotulo = geometria.representative_point()
            docs.append({
                "codigo": p.get("CIS_Geocod"),
                "nome": _texto(p.get("nome_atual")) or "(sem nome)",
                "bairro": _texto(p.get("Bairro_Pre")),
                "chave_bairro": normalizar(p.get("Bairro_Pre") or ""),
                "populacao_2014": _numero(p.get("Populacao_")),
                "area_ha": _numero(p.get("Area_ha")),
                "precariedade": _texto(p.get("Precarieda")),
                "zeis": _numero(p.get("ZEIS")),
                "prioritaria_sanear": _texto(p.get("Prioritari")) or None,
                "indicadores": {campo: _numero(p.get(campo)) for campo in INDICADORES},
                "geometria": mapping(geometria),
                "ponto_rotulo": [round(rotulo.x, 5), round(rotulo.y, 5)],
                "ano_levantamento": p.get("Ano"),
                "fonte": bruto["fonte"],
                "coletado_em": coletado_em,
            })
        # sem chaves: o cadastro da fonte é a verdade, substitui a tabela inteira
        return [Carga("silver.comunidades", docs)]
