"""Maré - nível do mar na costa do Recife, hora a hora.

Fonte: Open-Meteo Marine API, gratuita para uso não comercial, sem chave.

  bronze  bronze_mare           a resposta da API, uma por coleta
  silver  silver.mare_horaria   uma linha por hora (14 dias passados + 2 de previsão)

Por que maré: no Recife, alagamento na planície piora muito quando chuva
forte coincide com maré alta, porque a água não consegue escoar.

ATENÇÃO:
  - é MODELO, não marégrafo; serve para "maré alta / baixa", não como medição.
  - com cell_selection=sea a API usa a célula de mar mais próxima, ~16 km mar
    adentro. A maré chega ao estuário com atraso (estudo da UFPE no riacho
    Parnamirim mediu entre 19 e 47 minutos).
"""

from datetime import datetime, timedelta, timezone

from dominio.mare import preamares
from etl.base import Conector
from etl.comum.http import get_json
from etl.destinos.base import Carga

URL = "https://marine-api.open-meteo.com/v1/marine"
# ponto na costa do Recife; a API desloca para a célula de mar mais próxima
LATITUDE, LONGITUDE = -8.06, -34.85
# 14 dias cobrem um ciclo de sizígia/quadratura (~14,8 dias), base do critério relativo
DIAS_PASSADOS = 14
DIAS_PREVISAO = 2
# o Recife não tem horário de verão desde 2019: UTC-3 fixo
FUSO_RECIFE = timezone(timedelta(hours=-3))


class Mare(Conector):
    nome = "mare"
    frequencia = "diaria"
    descricao = "Nível do mar na costa do Recife, hora a hora (Open-Meteo Marine, modelo)"

    def extrair(self):
        return get_json(URL, {
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
            "cell_selection": "sea",  # sem isso a API pode cair numa célula de terra
            "hourly": "sea_level_height_msl",
            "past_days": DIAS_PASSADOS,
            "forecast_days": DIAS_PREVISAO,
            "timeformat": "unixtime",
            "timezone": "GMT",
        })

    def transformar(self, bruto, coletado_em):
        horario = bruto["hourly"]
        linhas = []
        for instante, nivel in zip(horario["time"], horario["sea_level_height_msl"]):
            hora = datetime.fromtimestamp(instante, tz=timezone.utc)
            linhas.append({
                "hora": hora,
                "nivel_m": nivel,
                "previsao": hora > coletado_em,
                "fonte": "open-meteo-marine",
                "tipo_dado": "modelo",
                "celula_lat": bruto["latitude"],
                "celula_lon": bruto["longitude"],
                "coletado_em": coletado_em,
            })
        niveis = [l["nivel_m"] for l in linhas if l["nivel_m"] is not None]
        if not niveis:
            raise ValueError("nível nulo em todas as horas: provável célula de terra (confira cell_selection=sea)")

        proximas = [p for p in preamares(linhas) if p["previsao"]][:3]
        print(f"  [{self.nome}] célula {bruto['latitude']}, {bruto['longitude']} | "
              f"{min(niveis):.2f} a {max(niveis):.2f} m | próximas cheias: "
              + ", ".join(f"{p['hora'].astimezone(FUSO_RECIFE):%d/%m %H:%M} {p['nivel_m']:.2f} m" for p in proximas))
        # upsert por hora: a previsão de uma hora vira valor consolidado quando ela passa
        return [Carga("silver.mare_horaria", linhas, chaves=("hora",))]
