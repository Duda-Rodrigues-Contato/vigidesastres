"""Previsão de chuva e temperatura por distrito - Open-Meteo (decisão 006).

Fonte: Open-Meteo (https://open-meteo.com), gratuito para uso não comercial.
É MODELO meteorológico, não medição: a tela deve dizer isso. A chuva medida
vem do CEMADEN; aqui fica só o que nenhuma fonte medida oferece: o futuro.

  bronze  bronze_previsao            a resposta da API, uma por coleta
  silver  silver.previsao_horaria    distrito x hora, das últimas 24 h às próximas 48 h
  gold    gold.previsao_distrito     por distrito: chuva prevista 24 h e 48 h, temperatura agora e
                                     o calor das próximas 24 h (índice de calor, dominio/calor.py)

Um ponto por distrito, garantidamente dentro do polígono. O modelo enxerga o
Recife em poucas células: distritos na mesma célula recebem a mesma previsão,
e a célula usada fica registrada em cada linha.
"""

from datetime import datetime, timedelta, timezone

from dominio.calor import CAUTELA_EXTREMA, indice_de_calor
from etl.base import Conector
from etl.comum.distritos import distritos_poligonos, nome_distrito
from etl.comum.http import get_json
from etl.destinos.base import Carga

URL = "https://api.open-meteo.com/v1/forecast"
FONTE = "Open-Meteo (modelo meteorológico, não medição)"


class Previsao(Conector):
    nome = "previsao"
    frequencia = "diaria"
    descricao = "Previsão de chuva e temperatura por distrito (Open-Meteo, modelo)"

    def extrair(self):
        pontos = []
        for codigo, poli in sorted(distritos_poligonos().items()):
            p = poli.representative_point()  # o centroide pode cair fora de polígono irregular
            pontos.append({"codigo": codigo, "lat": round(p.y, 5), "lon": round(p.x, 5)})
        resposta = get_json(URL, {
            "latitude": ",".join(str(p["lat"]) for p in pontos),
            "longitude": ",".join(str(p["lon"]) for p in pontos),
            "hourly": "precipitation,temperature_2m,relative_humidity_2m",
            "past_days": 1,       # a temperatura "agora" é a última hora passada
            # 3 e não 2: com 2 a janela à frente encurta conforme a hora da coleta
            "forecast_days": 3,
            "timeformat": "unixtime",
            "timezone": "GMT",
        })
        # com várias coordenadas a API devolve lista; com uma, objeto
        return {"pontos": pontos, "respostas": resposta if isinstance(resposta, list) else [resposta]}

    def documentos_bronze(self, bruto):
        return [bruto]

    def transformar(self, bruto, coletado_em):
        if len(bruto["respostas"]) != len(bruto["pontos"]):
            raise ValueError("a API devolveu um número de séries diferente do de distritos")
        linhas = []
        for ponto, r in zip(bruto["pontos"], bruto["respostas"]):
            h = r["hourly"]
            umidades = h.get("relative_humidity_2m") or [None] * len(h["time"])
            for instante, chuva, temp, umidade in zip(h["time"], h["precipitation"], h["temperature_2m"], umidades):
                hora = datetime.fromtimestamp(instante, tz=timezone.utc)
                linhas.append({
                    "distrito_codigo": ponto["codigo"], "distrito": nome_distrito(ponto["codigo"]),
                    "hora": hora, "chuva_mm": chuva, "temperatura_c": temp,
                    "umidade_pct": umidade, "indice_calor_c": indice_de_calor(temp, umidade),
                    "previsao": hora > coletado_em,
                    "celula_lat": r["latitude"], "celula_lon": r["longitude"],
                    "fonte": FONTE, "coletado_em": coletado_em,
                })
        celulas = {(round(r["latitude"], 3), round(r["longitude"], 3)) for r in bruto["respostas"]}
        print(f"  [{self.nome}] {len(bruto['pontos'])} distritos em {len(celulas)} células do modelo")
        # upsert: a previsão de cada hora é atualizada a cada coleta
        return [Carga("silver.previsao_horaria", linhas, chaves=("distrito_codigo", "hora"))]

    def agregar(self, cargas_silver, coletado_em):
        por_distrito = {}
        for l in cargas_silver[0].linhas:
            por_distrito.setdefault(l["distrito_codigo"], []).append(l)

        def soma(serie, horas):
            # valor de T = chuva da hora anterior: T em (agora, agora + N] cobre as próximas N horas
            fim = coletado_em + timedelta(hours=horas)
            return round(sum(l["chuva_mm"] or 0.0 for l in serie if coletado_em < l["hora"] <= fim), 1)

        def calor(serie):
            fim = coletado_em + timedelta(hours=24)
            prox = [l for l in serie if coletado_em < l["hora"] <= fim and l.get("indice_calor_c") is not None]
            if not prox:
                return {"temp_max_24h_c": None, "indice_calor_max_24h_c": None,
                        "horas_cautela_extrema_24h": None, "hora_pico_calor": None}
            pico = max(prox, key=lambda l: l["indice_calor_c"])
            return {"temp_max_24h_c": max(l["temperatura_c"] for l in prox),
                    "indice_calor_max_24h_c": pico["indice_calor_c"],
                    "horas_cautela_extrema_24h": sum(l["indice_calor_c"] >= CAUTELA_EXTREMA for l in prox),
                    "hora_pico_calor": pico["hora"]}

        gold = []
        for codigo, serie in sorted(por_distrito.items()):
            passadas = [l for l in serie if not l["previsao"] and l["temperatura_c"] is not None]
            gold.append({
                "distrito_codigo": codigo, "distrito": nome_distrito(codigo),
                "chuva_prox_24h_mm": soma(serie, 24), "chuva_prox_48h_mm": soma(serie, 48),
                "temperatura_c": passadas[-1]["temperatura_c"] if passadas else None,
                **calor(serie),
                "celula_lat": serie[0]["celula_lat"], "celula_lon": serie[0]["celula_lon"],
                "fonte": FONTE, "coletado_em": coletado_em,
            })
        print(f"  [{self.nome}] previsão 24 h: "
              + ", ".join(f"{g['distrito']} {g['chuva_prox_24h_mm']} mm" for g in gold))
        return [Carga("gold.previsao_distrito", gold, chaves=("distrito_codigo",))]
