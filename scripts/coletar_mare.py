"""
Conector de mare - nivel do mar na costa do Recife.

Fonte: Open-Meteo Marine API (https://open-meteo.com/en/docs/marine-weather-api),
gratuita para uso nao comercial, sem chave.

Por que mare: no Recife, alagamento na planicie piora muito quando chuva
forte coincide com mare alta, porque a agua nao consegue escoar para o mar.

ATENCAO:
  - e dado de MODELO, nao de mareografo. A propria documentacao avisa que a
    precisao em areas costeiras e limitada. Serve para dizer "mare alta /
    mare baixa", nao como medicao.
  - com cell_selection=sea a API usa a celula de mar mais proxima, que fica
    ~16 km mar adentro. A mare chega ao estuario com algum atraso (um estudo
    da UFPE no riacho Parnamirim mediu entre 19 e 47 minutos).

Padrao dos conectores do Vigidesastres:
  1. raw antes de normalizar
  2. `coletado_em` em todo documento
  3. buscar / normalizar / gravar separados
  4. gravacao idempotente (upsert por hora)

Uso:
    python scripts/coletar_mare.py
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import certifi
import requests
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.server_api import ServerApi

load_dotenv()

URL = "https://marine-api.open-meteo.com/v1/marine"
# ponto na costa do Recife; a API desloca para a celula de mar mais proxima
LATITUDE = -8.06
LONGITUDE = -34.85
# 14 dias cobrem um ciclo completo de sizigia/quadratura (~14,8 dias),
# base do criterio relativo de "mare alta" usado nos gatilhos
DIAS_PASSADOS = 14
DIAS_PREVISAO = 2

BANCO = "Recife"
COL_RAW = "raw_open_meteo_mare"
COL = "MareHorario"

HEADERS = {"User-Agent": "Vigidesastres/0.1 (projeto academico CESAR School)"}
# o Recife nao tem horario de verao desde 2019: UTC-3 fixo
FUSO_RECIFE = timezone(timedelta(hours=-3))


def conectar():
    uri = os.getenv("MONGO_URI")
    if not uri:
        sys.exit("ERRO: MONGO_URI nao encontrada. Confira o .env")
    cliente = MongoClient(uri, server_api=ServerApi("1"), tlsCAFile=certifi.where())
    cliente.admin.command("ping")
    return cliente


def buscar(tentativas=3):
    parametros = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "cell_selection": "sea",  # sem isso a API pode cair numa celula de terra
        "hourly": "sea_level_height_msl",
        "past_days": DIAS_PASSADOS,
        "forecast_days": DIAS_PREVISAO,
        "timeformat": "unixtime",
        "timezone": "GMT",
    }
    for tentativa in range(1, tentativas + 1):
        try:
            r = requests.get(URL, params=parametros, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as erro:
            if tentativa == tentativas:
                raise
            espera = 2**tentativa
            print(f"  falha ({erro}); nova tentativa em {espera}s...")
            time.sleep(espera)


def normalizar(resposta, coletado_em):
    horario = resposta["hourly"]
    registros = []
    for instante, nivel in zip(horario["time"], horario["sea_level_height_msl"]):
        hora = datetime.fromtimestamp(instante, tz=timezone.utc)
        registros.append(
            {
                "hora": hora,
                "nivel_m": nivel,
                "previsao": hora > coletado_em,
                "fonte": "open-meteo-marine",
                "tipo_dado": "modelo",
                "celula_lat": resposta["latitude"],
                "celula_lon": resposta["longitude"],
                "coletado_em": coletado_em,
            }
        )

    validos = [r for r in registros if r["nivel_m"] is not None]
    if not validos:
        sys.exit(
            "ERRO: a API devolveu nivel nulo em todas as horas.\n"
            "  Provavel celula de terra - confira o cell_selection=sea."
        )
    return registros


def preamares(registros):
    """Picos locais da serie (mare cheia). Dado horario: o pico real pode
    estar ate ~30 min antes ou depois da hora mostrada."""
    serie = [r for r in registros if r["nivel_m"] is not None]
    picos = []
    for anterior, atual, seguinte in zip(serie, serie[1:], serie[2:]):
        if atual["nivel_m"] > anterior["nivel_m"] and atual["nivel_m"] >= seguinte["nivel_m"]:
            picos.append(atual)
    return picos


def gravar(cliente, resposta, registros, coletado_em):
    banco = cliente[BANCO]
    banco[COL_RAW].insert_one(
        {"fonte": "open-meteo-marine", "coletado_em": coletado_em, "resposta": resposta}
    )
    print(f"RAW gravado em {BANCO}.{COL_RAW}")

    colecao = banco[COL]
    colecao.create_index("hora", unique=True, name="idx_hora")
    resultado = colecao.bulk_write(
        [UpdateOne({"hora": r["hora"]}, {"$set": r}, upsert=True) for r in registros]
    )
    print(
        f"OK: {resultado.upserted_count} horas novas, "
        f"{resultado.modified_count} atualizadas "
        f"({colecao.count_documents({})} no total em {BANCO}.{COL})"
    )


def resumo(resposta, registros):
    niveis = [r["nivel_m"] for r in registros if r["nivel_m"] is not None]
    print(
        f"\nCelula usada: lat {resposta['latitude']}, lon {resposta['longitude']}"
        f"\n{len(niveis)} horas | minimo {min(niveis):.2f} m | maximo {max(niveis):.2f} m"
        f" | amplitude {max(niveis) - min(niveis):.2f} m"
    )
    print("\nProximas mares cheias (horario do Recife):")
    for p in [p for p in preamares(registros) if p["previsao"]][:4]:
        local = p["hora"].astimezone(FUSO_RECIFE)
        print(f"  {local:%d/%m %H:%M}  {p['nivel_m']:.2f} m")


def main():
    coletado_em = datetime.now(timezone.utc)
    print("Consultando Open-Meteo Marine...")
    resposta = buscar()
    registros = normalizar(resposta, coletado_em)
    gravar(conectar(), resposta, registros, coletado_em)
    resumo(resposta, registros)
    print(f"\nColeta de {coletado_em.isoformat()} concluida.")


if __name__ == "__main__":
    main()