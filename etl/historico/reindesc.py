"""Ocorrências de inundação e deslizamento do REINDESC (CEMADEN): o alvo do modelo de eventos.

O REINDESC registra EVENTOS (com a data do evento), não atendimentos: é o que faltava
para o modelo de risco (decisão 010). Não tem API: os arquivos são exportados à mão em
reindesc.cemaden.gov.br (Tabela de ocorrências -> Exportar CSV) e colocados em
dados/reindesc/. A carga lê todos os .csv da pasta e descarta as ocorrências repetidas
(pelo ID da ocorrência).

  silver  silver.reindesc_ocorrencias   uma linha por ocorrência, com a UNIDADE do modelo:
          o distrito (Recife, pelas coordenadas) ou o município (vizinhos)

Uso:
    python -m etl.historico.reindesc
"""

import csv
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import Point

from dominio.rmr import VIZINHOS, unidade_do_distrito
from etl.comum.distritos import distrito_de, distritos_poligonos
from etl.comum.texto import normalizar
from etl.destinos import obter_destino
from etl.destinos.base import Carga

PASTA = Path(__file__).resolve().parents[2] / "dados" / "reindesc"
TABELA = "silver.reindesc_ocorrencias"
FONTE = "REINDESC - Registro de Eventos de Inundações e Deslizamentos do Cemaden"
NOMES_VIZINHOS = {normalizar(v[0]): v[0] for v in VIZINHOS.values()}


def _numero(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def ler_pasta(pasta=PASTA):
    """{id: linha} de todos os CSVs da pasta (repetidos aparecem uma vez só)."""
    ocorrencias = {}
    for arquivo in sorted(Path(pasta).glob("*.csv")):
        with open(arquivo, encoding="utf-8-sig", newline="") as f:
            for linha in csv.DictReader(f, delimiter=";"):
                if linha.get("ID ocorrência"):
                    ocorrencias[linha["ID ocorrência"]] = linha
    return ocorrencias


def transformar(ocorrencias, poligonos, coletado_em=None):
    linhas, fora = [], 0
    for oid, o in ocorrencias.items():
        municipio = normalizar(o.get("Município") or "")
        lat, lon = _numero(o.get("Latitude")), _numero(o.get("Longitude"))
        if municipio == "RECIFE":
            if lat is None or lon is None:
                fora += 1
                continue
            unidade = unidade_do_distrito(distrito_de(Point(lon, lat), poligonos))
        elif municipio in NOMES_VIZINHOS:
            unidade = NOMES_VIZINHOS[municipio]
        else:
            fora += 1
            continue
        data = datetime.strptime(o["Data"][:10], "%Y-%m-%d")
        linhas.append({"id": int(oid), "data": data, "ano": data.year, "unidade": unidade,
                       "municipio": o.get("Município"), "tipologia": o.get("Tipologia"),
                       "magnitude": o.get("Magnitude"), "precisao": o.get("Precisão"),
                       "precisao_horario": o.get("Precisão do horário"),
                       "horario_utc": o.get("Horário da ocorrência (UTC)") or None,
                       "latitude": lat, "longitude": lon, "fonte": FONTE, "coletado_em": coletado_em})
    return linhas, fora


def carregar(destino, pasta=PASTA, poligonos=None, avisar=print):
    ocorrencias = ler_pasta(pasta)
    if not ocorrencias:
        raise ValueError(f"nenhum CSV do REINDESC em {pasta}: exporte em reindesc.cemaden.gov.br e coloque lá")
    linhas, fora = transformar(ocorrencias, poligonos or distritos_poligonos(), datetime.now(timezone.utc))
    destino.carregar(Carga(TABELA, linhas, chaves=("id",)))
    por_unidade = {}
    for l in linhas:
        por_unidade[l["unidade"]] = por_unidade.get(l["unidade"], 0) + 1
    avisar(f"{len(linhas)} ocorrências ({fora} fora das unidades ou sem coordenada)")
    for u, n in sorted(por_unidade.items(), key=lambda p: -p[1]):
        avisar(f"  {u:<26} {n}")


if __name__ == "__main__":
    carregar(obter_destino())
