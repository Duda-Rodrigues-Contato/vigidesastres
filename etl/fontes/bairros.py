"""Bairros do Recife: limite e população, num lugar só para várias camadas.

Fontes: limites - Portal de Dados Abertos do Recife; população - IBGE, Censo 2022.

  bronze  bronze_bairros     as linhas do IBGE do Recife (dado público e agregado)
  silver  silver.bairros     um bairro por documento: nome, chave, população, área, geometria

Cadastro de referência: cada carga substitui a anterior.
"""

from collections import defaultdict

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from etl.base import Conector
from etl.comum import ibge
from etl.comum.bairros import baixar_bairros, para_latlon
from etl.comum.texto import normalizar
from etl.destinos.base import Carga


class Bairros(Conector):
    nome = "bairros"
    frequencia = "anual"
    descricao = "Limites e população dos bairros (portal do Recife + IBGE Censo 2022)"

    def extrair(self):
        return {"ibge": ibge.linhas_do_recife(), "limites": baixar_bairros()}

    def documentos_bronze(self, bruto):
        return bruto["ibge"]

    def transformar(self, bruto, coletado_em):
        populacao = ibge.populacao_por_bairro(bruto["ibge"])
        features = bruto["limites"]
        converter = para_latlon(features)

        # o arquivo de limites traz o nome em mais de um campo, e nem sempre
        # igual ao do IBGE (ex.: "COHAB" num campo, "Cohab - Ibura de Cima" no
        # outro): o bairro casa se QUALQUER campo de texto bater com o IBGE
        geometrias = defaultdict(list)
        for f in features:
            nomes = {normalizar(v) for v in f["properties"].values() if isinstance(v, str)}
            for chave in nomes & set(populacao):
                geometrias[chave].append(converter(shape(f["geometry"])))

        docs, sem_limite = [], []
        for chave, b in sorted(populacao.items()):
            if chave not in geometrias:
                sem_limite.append(b["nome"])
                continue
            docs.append({**b, "chave": chave, "geometria": mapping(unary_union(geometrias[chave])),
                         "fonte_populacao": ibge.FONTE, "coletado_em": coletado_em})
        total = sum(d["populacao"] for d in docs)
        print(f"  [{self.nome}] {len(docs)} bairros, {total:,} habitantes".replace(",", ".")
              + (f" | sem limite no mapa: {sem_limite}" if sem_limite else ""))
        return [Carga("silver.bairros", docs)]
