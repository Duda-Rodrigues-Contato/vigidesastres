"""Rede de apoio: abrigos, escolas municipais e CRAS do Recife.

Fonte: Portal de Dados Abertos do Recife
  - "Abrigos - Chuvas no Recife - Acolhimento"   (cadastro, sem capacidade)
  - "Unidades educacionais no município"          (escolas viram abrigo)
  - "Centros de Referência de Assistência Social" (quem opera abrigos)

  bronze  bronze_rede_apoio     as linhas de cada tabela, com o tipo
  silver  silver.rede_apoio     um ponto por equipamento

Todos são endereços de equipamentos públicos, não de pessoas. O cadastro de
abrigos diz ONDE eles ficam, não se estão ABERTOS agora nem QUANTAS pessoas
cabem: esses números ainda dependem da Assistência Social.
"""

from collections import Counter

from etl.base import Conector
from etl.comum.ckan import dataset_por_titulo
from etl.comum.tabela import ler_recurso
from etl.destinos.base import Carga

# caixa que envolve o Recife, com folga; ponto fora dela é contado, não desenhado
LAT_MIN, LAT_MAX = -8.20, -7.90
LON_MIN, LON_MAX = -35.05, -34.80

# tipo -> (busca, trecho do título, filtro CKAN)
BUSCAS = {
    "abrigo": ("abrigos", "abrigos", None),
    "escola": ("unidades educacionais", "unidades educacionais", None),
    "cras": ("*:*", "assist", "tags:CREAS"),
}


def campo(linha, *pistas, evitar=()):
    """Primeira coluna cujo nome contém alguma das pistas."""
    for chave in linha:
        nome = chave.lower()
        if any(p in nome for p in pistas) and not any(e in nome for e in evitar):
            return chave
    return None


def numero(valor):
    try:
        return float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def no_recife(lat, lon):
    return LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX


def pontos(tipo, linhas, fonte, coletado_em):
    """Linhas de uma tabela -> pontos válidos, mais a contagem do que ficou de fora."""
    conta = Counter()
    if not linhas:
        return [], conta
    exemplo = linhas[0]
    c_nome = campo(exemplo, "nome", "equipamento", "unidade", evitar=("municip",))
    c_bairro = campo(exemplo, "bairro")
    c_end = campo(exemplo, "endereco", "endereço", "logradouro")
    c_num = "N" if "N" in exemplo else campo(exemplo, "numero", "número")
    c_lat, c_lon = campo(exemplo, "lat"), campo(exemplo, "lon", "lng")
    if not (c_lat and c_lon):
        conta["sem_colunas_de_coordenada"] = len(linhas)
        return [], conta

    extras = [c for c in exemplo if c not in {c_nome, c_bairro, c_end, c_num, c_lat, c_lon, "_id"}]
    docs = []
    for l in linhas:
        lat, lon = numero(l.get(c_lat)), numero(l.get(c_lon))
        if lat is None or lon is None:
            conta["sem_coordenada"] += 1
            continue
        if not no_recife(lat, lon) and no_recife(lon, lat):
            lat, lon = lon, lat  # latitude e longitude trocadas na origem
            conta["invertidas"] += 1
        if not no_recife(lat, lon):
            conta["fora_do_recife"] += 1
            continue
        endereco = (l.get(c_end) or "").strip()
        if c_num and str(l.get(c_num) or "").strip():
            endereco += f", {str(l[c_num]).strip()}"
        docs.append({
            "tipo": tipo,
            "nome": (l.get(c_nome) or "").strip() or "(sem nome)",
            "bairro": (l.get(c_bairro) or "").strip(),
            "endereco": endereco,
            "detalhe": {c: l.get(c) for c in extras if str(l.get(c) or "").strip()},
            "localizacao": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "fonte": fonte,
            "coletado_em": coletado_em,
        })
        conta["ok"] += 1
    return docs, conta


class RedeApoio(Conector):
    nome = "rede_apoio"
    frequencia = "anual"
    descricao = "Abrigos, escolas municipais e CRAS (portal do Recife)"

    def extrair(self):
        """{tipo: {fonte, recurso, linhas}}. Um tipo que falta não derruba os outros."""
        bruto = {}
        for tipo, (busca, trecho, filtro) in BUSCAS.items():
            pacote = dataset_por_titulo(busca, trecho, filtro)
            csvs = [r for r in (pacote or {}).get("resources", []) if (r.get("format") or "").upper() == "CSV"]
            if not csvs:
                print(f"  [{self.nome}] {tipo}: dataset ou CSV não encontrado no portal")
                continue
            recurso = sorted(csvs, key=lambda r: r.get("name") or "")[-1]  # o nome costuma trazer o ano
            bruto[tipo] = {"fonte": pacote["title"], "recurso": recurso.get("name"),
                           "linhas": ler_recurso(recurso)}
        if not bruto:
            raise ValueError("nenhuma tabela da rede de apoio encontrada no portal")
        return bruto

    def documentos_bronze(self, bruto):
        # linhas do datastore trazem "_id" próprio, que colidiria com o _id do Mongo
        return [{"_tipo": tipo, **{("_id_ckan" if k == "_id" else k): v for k, v in l.items()}}
                for tipo, t in bruto.items() for l in t["linhas"]]

    def transformar(self, bruto, coletado_em):
        todos = []
        for tipo, t in bruto.items():
            docs, conta = pontos(tipo, t["linhas"], t["fonte"], coletado_em)
            print(f"  [{self.nome}] {tipo:<7} {t['recurso']}: {len(t['linhas'])} linhas -> {dict(conta)}")
            todos += docs
        if not todos:
            raise ValueError("nenhum ponto válido na rede de apoio")
        # sem chaves: o portal é a verdade, substitui a tabela inteira
        return [Carga("silver.rede_apoio", todos)]
