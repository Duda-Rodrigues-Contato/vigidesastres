"""Distritos sanitários do Recife - os 8 polígonos (desde 2014).

Fonte: Portal de Dados Abertos do Recife, dataset "distritos-sanitarios".

  bronze  bronze_distritos                o GeoJSON como veio
  silver  silver.distritos_sanitarios     uma Feature GeoJSON por distrito

Cadastro de referência: muda raramente, e cada carga substitui a anterior.
As Features ficam no formato GeoJSON porque o mapa (Leaflet) e o conector
de meteorologia leem assim. O código do distrito vem em properties.cdistscodi
(1 a 8); "DS I".."DS VIII" é montado na tela.
"""

import json

from etl.base import Conector
from etl.comum.ckan import pacote_por_id, recurso_por_formato
from etl.comum.http import get_bytes
from etl.destinos.base import Carga

DATASET = "distritos-sanitarios"
TOTAL_ESPERADO = 8


class Distritos(Conector):
    nome = "distritos"
    frequencia = "anual"
    descricao = "Polígonos dos 8 distritos sanitários (portal do Recife)"

    def extrair(self):
        recurso = recurso_por_formato(pacote_por_id(DATASET), "GEOJSON")
        return json.loads(get_bytes(recurso["url"]))

    def transformar(self, bruto, coletado_em):
        features = bruto.get("features") or []
        if not features:
            raise ValueError("GeoJSON dos distritos veio sem features")
        if "cdistscodi" not in (features[0].get("properties") or {}):
            raise ValueError("campo cdistscodi ausente: o mapa e o meteo dependem dele")
        if len(features) != TOTAL_ESPERADO:
            print(f"  [{self.nome}] atenção: {len(features)} distritos (esperado {TOTAL_ESPERADO})")
        linhas = [{"type": "Feature", "properties": f.get("properties") or {},
                   "geometry": f["geometry"]} for f in features]
        # sem chaves: o arquivo da fonte é a verdade, substitui a tabela inteira
        return [Carga("silver.distritos_sanitarios", linhas)]
