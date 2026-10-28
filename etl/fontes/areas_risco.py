"""Áreas de risco alto e muito alto (R3/R4), agrupadas por bairro.

Fontes:
  - Plano de Contingência 2024 da Defesa Civil do Recife (SEDEC), Quadros 04
    e 05, transcritos à mão em data/areas_risco_placon2024.csv
  - limites dos bairros: Portal de Dados Abertos do Recife

  bronze  bronze_areas_risco    as linhas da planilha (a transcrição é a fonte)
  silver  silver.areas_risco    um bairro por documento, com as localidades

O plano aponta COMUNIDADES dentro dos bairros, não bairros inteiros. A camada
diz "este bairro CONTÉM áreas de risco"; o detalhe lista quais.
"""

import csv
from datetime import datetime, timezone

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from dominio.bairros import APELIDOS_PLANO
from etl import config
from etl.base import Conector
from etl.comum.bairros import baixar_bairros, campo_do_nome, para_latlon
from etl.comum.texto import normalizar
from etl.destinos.base import Carga

CSV_PLANO = config.RAIZ / "data" / "areas_risco_placon2024.csv"
FONTE = "Plano de Contingência 2024 — Defesa Civil do Recife (SEDEC)"


def ler_planilha(caminho=CSV_PLANO):
    with open(caminho, encoding="utf-8") as f:
        return list(csv.DictReader(f))


class AreasRisco(Conector):
    nome = "areas_risco"
    frequencia = "anual"
    descricao = "Bairros com áreas R3/R4 (Plano de Contingência 2024)"

    def extrair(self):
        return {"planilha": ler_planilha(), "bairros": baixar_bairros()}

    def documentos_bronze(self, bruto):
        # os limites dos bairros são de outra fonte e serão bronze do conector de bairros
        return bruto["planilha"]

    def transformar(self, bruto, coletado_em):
        linhas, features = bruto["planilha"], bruto["bairros"]
        conhecidos = {normalizar(l["bairro"]) for l in linhas}
        for destinos in APELIDOS_PLANO.values():
            conhecidos.update(destinos)
        campo = campo_do_nome(features, conhecidos)
        converter = para_latlon(features)

        geometrias, nome_oficial = {}, {}
        for f in features:
            chave = normalizar(f["properties"].get(campo) or "")
            geometrias.setdefault(chave, []).append(converter(shape(f["geometry"])))
            nome_oficial[chave] = f["properties"][campo]

        por_bairro, sem_par = {}, set()
        for l in linhas:
            nome_plano = normalizar(l["bairro"])
            for destino in APELIDOS_PLANO.get(nome_plano, [nome_plano]):
                if destino not in geometrias:
                    sem_par.add(l["bairro"])
                    continue
                b = por_bairro.setdefault(destino, {"deslizamento": [], "alagamento": []})
                item = l["localidade"] + (f" ({l['bairro']})" if nome_plano != destino else "")
                b[l["tipo"]].append(item)
        if sem_par:
            print(f"  [{self.nome}] bairros do plano sem par no mapa (ver dominio/bairros.py): {sorted(sem_par)}")

        docs = []
        for chave, riscos in sorted(por_bairro.items()):
            geometria = unary_union(geometrias[chave])
            rotulo = geometria.representative_point()
            docs.append({
                "bairro": nome_oficial[chave],
                "chave": chave,
                "tipos": [t for t in ("alagamento", "deslizamento") if riscos[t]],
                "alagamento": riscos["alagamento"],
                "deslizamento": riscos["deslizamento"],
                "total_areas": len(riscos["alagamento"]) + len(riscos["deslizamento"]),
                "nivel": "R3/R4 (alto ou muito alto)",
                "geometria": mapping(geometria),
                "ponto_rotulo": [round(rotulo.x, 5), round(rotulo.y, 5)],
                "fonte": FONTE,
                "coletado_em": coletado_em,
            })
        # sem chaves: a planilha é a verdade, substitui a tabela inteira
        return [Carga("silver.areas_risco", docs)]
