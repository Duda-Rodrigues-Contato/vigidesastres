"""Polígonos dos 8 distritos sanitários, baixados do portal do Recife.

Usado pelos conectores que precisam ligar um ponto (estação, célula do
modelo) a um distrito. O cadastro em si é gravado pelo conector `distritos`.
"""

import json

from shapely.geometry import shape

from etl.comum.ckan import pacote_por_id, recurso_por_formato
from etl.comum.http import get_bytes

from dominio.distritos import nome_distrito  # noqa: F401  (reexportado para os conectores)

DATASET = "distritos-sanitarios"


def distritos_poligonos():
    """{codigo: polígono shapely} dos 8 distritos."""
    recurso = recurso_por_formato(pacote_por_id(DATASET), "GEOJSON")
    features = json.loads(get_bytes(recurso["url"]))["features"]
    return {f["properties"]["cdistscodi"]: shape(f["geometry"]) for f in features}


def distrito_de(geometria, poligonos):
    """Código do distrito que cobre a maior parte da geometria (bairro na divisa fica no maior pedaço)."""
    areas = {codigo: geometria.intersection(poli).area for codigo, poli in poligonos.items()}
    codigo, area = max(areas.items(), key=lambda par: par[1])
    if area > 0:
        return codigo
    # fora de todos (erro de borda no litoral): o distrito mais próximo
    return min(poligonos, key=lambda c: poligonos[c].distance(geometria))
