"""Limites dos bairros do Recife: download e preparo das geometrias.

Usado por mais de um conector (áreas de risco, arboviroses por bairro).
Antes morava em scripts/seed_areas_risco.py e era importado de lá.
"""

import json

import numpy as np
import shapely
from shapely.geometry import shape

from etl.comum.ckan import pacote_por_id
from etl.comum.http import get_bytes
from etl.comum.texto import normalizar

DATASET_BAIRROS = "mapas-de-limites-e-divisoes-territoriais"


def baixar_bairros():
    """As Features GeoJSON dos bairros, como o portal publica (pode vir em UTM)."""
    pacote = pacote_por_id(DATASET_BAIRROS)
    candidatos = [r for r in pacote["resources"]
                  if (r.get("format") or "").upper() == "GEOJSON" and "bairro" in (r.get("name") or "").lower()]
    if not candidatos:
        nomes = ", ".join(f"{r.get('name')} [{r.get('format')}]" for r in pacote["resources"])
        raise ValueError(f"nenhum GeoJSON de bairros no dataset; recursos: {nomes}")
    return json.loads(get_bytes(candidatos[0]["url"], timeout=120))["features"]


def campo_do_nome(features, nomes_conhecidos):
    """Qual propriedade traz o nome do bairro: a que mais casa com nomes conhecidos.

    O portal costuma ter o nome em duas versões ("IBURA" e "Ibura"). No empate,
    prefere a grafia com minúsculas e acentos, para o mapa não gritar.
    """
    placar = {}
    for campo in features[0]["properties"]:
        valores = {normalizar(f["properties"].get(campo) or "") for f in features}
        placar[campo] = len(valores & nomes_conhecidos)

    acertos = max(placar.values(), default=0)
    empatados = [c for c, n in placar.items() if n == acertos and n > 0]
    if not empatados:
        raise ValueError(f"nenhuma propriedade parece ser o nome do bairro: {list(features[0]['properties'])}")

    def grafia_normal(campo):
        return sum(1 for f in features if any(ch.islower() for ch in str(f["properties"].get(campo) or "")))

    return max(empatados, key=grafia_normal)


def para_latlon(features):
    """Função que converte uma geometria shapely para lat/long, se preciso.

    A prefeitura publica em SIRGAS 2000 / UTM 25S (EPSG:31985); o Leaflet
    exige lat/long (EPSG:4326).
    """
    x, y = shape(features[0]["geometry"]).representative_point().coords[0]
    if abs(x) <= 180 and abs(y) <= 90:
        return lambda geom: geom

    from pyproj import Transformer

    conversor = Transformer.from_crs("EPSG:31985", "EPSG:4326", always_xy=True)

    def converter(geom):
        def coords(xy):
            lon, lat = conversor.transform(xy[:, 0], xy[:, 1])
            return np.column_stack([lon, lat])
        return shapely.transform(geom, coords)

    return converter
