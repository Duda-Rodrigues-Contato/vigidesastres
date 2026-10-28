"""Polígonos dos 8 distritos sanitários, baixados do portal do Recife.

Usado pelos conectores que precisam ligar um ponto (estação, célula do
modelo) a um distrito. O cadastro em si é gravado pelo conector `distritos`.
"""

import json

from shapely.geometry import shape

from etl.comum.ckan import pacote_por_id, recurso_por_formato
from etl.comum.http import get_bytes

DATASET = "distritos-sanitarios"
ROMANOS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]


def nome_distrito(codigo):
    return f"DS {ROMANOS[codigo - 1]}" if 1 <= codigo <= len(ROMANOS) else f"DS {codigo}"


def distritos_poligonos():
    """{codigo: polígono shapely} dos 8 distritos."""
    recurso = recurso_por_formato(pacote_por_id(DATASET), "GEOJSON")
    features = json.loads(get_bytes(recurso["url"]))["features"]
    return {f["properties"]["cdistscodi"]: shape(f["geometry"]) for f in features}
