"""CNES - unidades de saúde do Recife (história US-ID-04, dados assistenciais).

Fonte: API de Dados Abertos do Ministério da Saúde
https://apidadosabertos.saude.gov.br

  bronze  bronze_cnes              o cadastro COMPLETO, um estabelecimento por documento
  silver  silver.unidades_saude    só as unidades de resposta (dominio/saude.py)

O bronze guarda sempre o cadastro inteiro: mudar o recorte depois não exige
coletar de novo. A API ignora limit acima de 20, então são centenas de páginas.
"""

from collections import Counter

from dominio.saude import TIPOS_RESPOSTA
from etl.base import Conector
from etl.comum.http import get_json
from etl.destinos.base import Carga

BASE = "https://apidadosabertos.saude.gov.br/cnes"
CODIGO_MUNICIPIO_RECIFE = 261160  # IBGE sem dígito verificador, como a API pede
TAMANHO_PAGINA = 20
MAX_PAGINAS = 1000  # trava de segurança: 20 mil estabelecimentos


def _coordenada(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


class Cnes(Conector):
    nome = "cnes"
    frequencia = "anual"
    descricao = "Unidades de saúde de resposta a emergência (CNES/Ministério da Saúde)"

    def __init__(self, destino, todos=False):
        super().__init__(destino)
        self.todos = todos  # True: silver com o cadastro inteiro, não só as de resposta

    def extrair(self):
        tipos = {t["codigo_tipo_unidade"]: t["descricao_tipo_unidade"]
                 for t in get_json(f"{BASE}/tipounidades", {"limit": 200}).get("tipos_unidade", [])}
        estabelecimentos = []
        for pagina in range(MAX_PAGINAS):
            lote = get_json(f"{BASE}/estabelecimentos", {
                "codigo_municipio": CODIGO_MUNICIPIO_RECIFE,
                "limit": TAMANHO_PAGINA, "offset": pagina * TAMANHO_PAGINA,
            }).get("estabelecimentos", [])
            # só uma página vazia indica o fim: a API pode devolver menos que o limit
            if not lote:
                break
            estabelecimentos += lote
        else:
            raise ValueError(f"parou na trava de {MAX_PAGINAS} páginas: coleta incompleta")
        if not estabelecimentos:
            raise ValueError("a API do CNES não devolveu nenhum estabelecimento")
        return {"tipos": tipos, "estabelecimentos": estabelecimentos}

    def documentos_bronze(self, bruto):
        # um documento por estabelecimento: tudo num só estouraria os 16 MB do BSON
        return bruto["estabelecimentos"]

    def transformar(self, bruto, coletado_em):
        tipos, todos = bruto["tipos"], bruto["estabelecimentos"]
        escolhidos = todos if self.todos else [e for e in todos if e.get("codigo_tipo_unidade") in TIPOS_RESPOSTA]

        unidades = []
        for e in escolhidos:
            lat = _coordenada(e.get("latitude_estabelecimento_decimo_grau"))
            lon = _coordenada(e.get("longitude_estabelecimento_decimo_grau"))
            codigo_tipo = e.get("codigo_tipo_unidade")
            unidades.append({
                "codigo_cnes": e.get("codigo_cnes"),
                "nome": e.get("nome_fantasia") or e.get("nome_razao_social"),
                "bairro": e.get("bairro_estabelecimento"),
                "endereco": e.get("endereco_estabelecimento"),
                "codigo_tipo": codigo_tipo,
                "tipo": tipos.get(codigo_tipo),
                "atende_hospitalar": e.get("estabelecimento_possui_atendimento_hospitalar"),
                "turno": e.get("descricao_turno_atendimento"),
                # GeoJSON Point é [lon, lat], nessa ordem
                "localizacao": ({"type": "Point", "coordinates": [lon, lat]}
                                if lat is not None and lon is not None else None),
                "atualizado_na_fonte": e.get("data_atualizacao"),
                "coletado_em": coletado_em,
            })

        sem_coord = sum(1 for u in unidades if u["localizacao"] is None)
        por_tipo = Counter(u["tipo"] for u in unidades).most_common(5)
        print(f"  [{self.nome}] {len(unidades)} de {len(todos)} estabelecimentos | "
              f"{sem_coord} sem coordenada (não aparecem no mapa) | mais comuns: {por_tipo}")
        # sem chaves: o cadastro da fonte é a verdade, substitui a tabela inteira
        return [Carga("silver.unidades_saude", unidades)]
