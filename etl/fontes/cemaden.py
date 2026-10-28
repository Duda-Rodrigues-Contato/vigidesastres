"""CEMADEN - chuva medida pelos pluviômetros do Recife (decisão 006).

Fonte: Plataforma de Entrega de Dados do CEMADEN (cadastro gratuito).
"Dados da Rede Observacional do CEMADEN/MCTIC" - citação obrigatória na tela.

  bronze  bronze_cemaden                 o CSV de cada estação, um documento por estação e coleta
  silver  silver.chuva_leituras          uma leitura por estação e horário (10 min com chuva, 1 h sem)
  silver  silver.chuva_estacoes          cadastro: nome, coordenada, distrito, última leitura
  gold    gold.chuva_distrito_hora       chuva por distrito e hora: média e máximo das estações

Cada coleta baixa os últimos DIAS dias de cada estação (1 requisição por
estação, limite de 12 por minuto): cobre o gráfico de 14 dias e preenche
qualquer coleta perdida. Upsert por (estação, horário): repetir não duplica.

Distrito sem pluviômetro usa a estação mais próxima, marcada como tal.
"""

import json
from datetime import datetime, timedelta, timezone

from shapely.geometry import Point, shape

from etl.base import Conector
from etl.comum.cemaden import FONTE, ClienteCemaden, ler_serie
from etl.comum.ckan import pacote_por_id, recurso_por_formato
from etl.comum.http import get_bytes
from etl.destinos.base import Carga
from etl.fontes.distritos import DATASET as DATASET_DISTRITOS

CODIBGE_RECIFE = "2611606"
UF = "PE"
DIAS = 15
# relógio de estação adiantado: leitura além disso no futuro é descartada
TOLERANCIA_FUTURO = timedelta(minutes=15)


def _numero(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _hora_fechada(dt):
    """Leitura das 00:10 é chuva de 00:00-00:10 -> conta na hora que termina às 01:00
    (mesma convenção do Open-Meteo: o valor de T é a chuva da hora anterior)."""
    cheia = dt.replace(minute=0, second=0, microsecond=0)
    return cheia if dt == cheia else cheia + timedelta(hours=1)


def distritos_poligonos():
    """{codigo: polígono shapely} dos 8 distritos, do portal do Recife."""
    recurso = recurso_por_formato(pacote_por_id(DATASET_DISTRITOS), "GEOJSON")
    features = json.loads(get_bytes(recurso["url"]))["features"]
    return {f["properties"]["cdistscodi"]: shape(f["geometry"]) for f in features}


class Cemaden(Conector):
    nome = "cemaden"
    frequencia = "diaria"
    descricao = "Chuva medida nos pluviômetros do Recife (CEMADEN)"

    def __init__(self, destino, dias=DIAS, cliente=None):
        super().__init__(destino)
        self.dias = dias
        self.cliente = cliente

    def extrair(self):
        cliente = self.cliente or ClienteCemaden()
        cadastro = cliente.estacoes_do_municipio(CODIBGE_RECIFE, UF)
        if not cadastro:
            raise ValueError("cadastro do CEMADEN sem estações para o Recife")
        fim = datetime.now(timezone.utc)
        inicio = fim - timedelta(days=self.dias)
        series = {e["codestacao"]: cliente.serie_csv(e["codestacao"], UF, inicio, fim) for e in cadastro}
        return {"cadastro": cadastro, "series": series, "distritos": distritos_poligonos()}

    def documentos_bronze(self, bruto):
        return [{"codestacao": c, "csv": t} for c, t in bruto["series"].items() if t]

    def transformar(self, bruto, coletado_em):
        limite = coletado_em + TOLERANCIA_FUTURO
        leituras, estacoes, descartes = [], [], {"futuro": 0, "sem_valor": 0}
        for e in bruto["cadastro"]:
            linhas = ler_serie(bruto["series"].get(e["codestacao"], ""))
            ultima, lat, lon = None, None, None
            for l in linhas:
                dt = datetime.strptime(l["datahora"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                valor = _numero(l.get("valor"))
                if dt > limite:
                    descartes["futuro"] += 1
                    continue
                if valor is None:
                    descartes["sem_valor"] += 1
                    continue
                lat, lon = _numero(l.get("latitude")), _numero(l.get("longitude"))
                ultima = max(ultima or dt, dt)
                leituras.append({"codestacao": e["codestacao"], "datahora": dt, "hora": _hora_fechada(dt),
                                 "chuva_mm": valor, "qualificacao": (l.get("qualificacao") or "").strip(),
                                 "coletado_em": coletado_em})
            estacoes.append({"codestacao": e["codestacao"], "nome": e["nome"], "tipo": e.get("id_tipoestacao"),
                             "latitude": lat, "longitude": lon, "ultima_leitura": ultima,
                             "ativa": ultima is not None, "fonte": FONTE, "coletado_em": coletado_em})

        self._distritos(estacoes, bruto["distritos"])
        ativas = sum(e["ativa"] for e in estacoes)
        print(f"  [{self.nome}] {ativas} de {len(estacoes)} estações com dados | "
              f"{len(leituras)} leituras | descartadas: {descartes}")
        if not leituras:
            raise ValueError("nenhuma leitura de chuva no período: CEMADEN fora do ar ou credencial inválida?")
        return [
            Carga("silver.chuva_leituras", leituras, chaves=("codestacao", "datahora")),
            Carga("silver.chuva_estacoes", estacoes),  # cadastro: substitui
        ]

    def _distritos(self, estacoes, poligonos):
        """Põe em cada estação o distrito onde ela fica (ou o mais perto, se cair fora)."""
        for e in estacoes:
            if e["latitude"] is None:
                e["distrito_codigo"] = None
                continue
            p = Point(e["longitude"], e["latitude"])
            dentro = [c for c, poli in poligonos.items() if poli.contains(p)]
            e["distrito_codigo"] = dentro[0] if dentro else min(poligonos, key=lambda c: poligonos[c].distance(p))
        # distrito sem estação: herda a ativa mais próxima do seu centro
        self.cobertura = {}
        ativas = [e for e in estacoes if e["ativa"]]
        for codigo, poli in poligonos.items():
            proprias = [e["codestacao"] for e in ativas if e["distrito_codigo"] == codigo]
            if proprias:
                self.cobertura[codigo] = {"estacoes": proprias, "estacao_proxima": False}
            elif ativas:
                centro = poli.representative_point()
                perto = min(ativas, key=lambda e: Point(e["longitude"], e["latitude"]).distance(centro))
                self.cobertura[codigo] = {"estacoes": [perto["codestacao"]], "estacao_proxima": True}

    def agregar(self, cargas_silver, coletado_em):
        leituras = cargas_silver[0].linhas
        # chuva por estação e hora
        por_estacao_hora = {}
        for l in leituras:
            chave = (l["codestacao"], l["hora"])
            por_estacao_hora[chave] = por_estacao_hora.get(chave, 0.0) + l["chuva_mm"]
        horas = sorted({h for _, h in por_estacao_hora})

        gold = []
        for codigo, cob in sorted(self.cobertura.items()):
            for hora in horas:
                valores = {c: por_estacao_hora[(c, hora)] for c in cob["estacoes"] if (c, hora) in por_estacao_hora}
                if not valores:
                    continue  # nenhuma estação mediu nessa hora: lacuna, não zero
                pior = max(valores, key=valores.get)
                gold.append({
                    "distrito_codigo": codigo, "hora": hora,
                    "chuva_media_mm": round(sum(valores.values()) / len(valores), 2),
                    "chuva_max_mm": round(valores[pior], 2), "estacao_max": pior,
                    "estacoes_com_dado": len(valores), "estacao_proxima": cob["estacao_proxima"],
                    "fonte": FONTE, "coletado_em": coletado_em,
                })
        sem = [c for c, cob in self.cobertura.items() if cob["estacao_proxima"]]
        if sem:
            print(f"  [{self.nome}] distritos sem pluviômetro próprio (usam o mais próximo): {sorted(sem)}")
        return [Carga("gold.chuva_distrito_hora", gold, chaves=("distrito_codigo", "hora"))]
