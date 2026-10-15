"""
Conector Open-Meteo - chuva e temperatura por distrito sanitario.

Fonte: Open-Meteo (https://open-meteo.com), gratuito para uso nao
comercial, sem chave. Substitui o INMET, cuja API de leitura esta fechada.

ATENCAO: sao dados de MODELO meteorologico, nao medicao de estacao.
A interface deve deixar isso explicito.

Atende a historia US-ID-01 (dados meteorologicos).

Padrao dos conectores do Vigidesastres:
  1. raw antes de normalizar
  2. `coletado_em` em todo documento
  3. buscar / normalizar / gravar separados
  4. gravacao idempotente: rodar de novo atualiza, nao duplica

Uso:
    python scripts/coletar_meteo.py
"""

import os
import sys
import time
from datetime import datetime, timezone

import certifi
import requests
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.server_api import ServerApi
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

load_dotenv()

URL = "https://api.open-meteo.com/v1/forecast"
DIAS_PASSADOS = 7  # janela de historico recente por coleta
DIAS_PREVISAO = 1

BANCO = "Recife"
COL_DISTRITOS = "DistritosSanitarios"
COL_RAW = "raw_open_meteo"
COL = "MeteoHorario"
COL_ZONAS = "ZonasChuva"

HEADERS = {"User-Agent": "Vigidesastres/0.1 (projeto academico CESAR School)"}
ROMANOS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]


def nome_distrito(codigo):
    return f"DS {ROMANOS[codigo - 1]}" if 1 <= codigo <= len(ROMANOS) else f"DS {codigo}"


def conectar():
    uri = os.getenv("MONGO_URI")
    if not uri:
        sys.exit("ERRO: MONGO_URI nao encontrada. Confira o .env")
    cliente = MongoClient(uri, server_api=ServerApi("1"), tlsCAFile=certifi.where())
    cliente.admin.command("ping")
    return cliente


def pontos_dos_distritos(cliente):
    """Um ponto por distrito, garantidamente DENTRO do poligono.

    O centroide de um poligono irregular pode cair fora dele.
    representative_point() do shapely garante um ponto interno.
    """
    pontos = []
    for d in cliente[BANCO][COL_DISTRITOS].find({}, {"_id": 0}):
        poligono = shape(d["geometry"])
        ponto = poligono.representative_point()
        codigo = d["properties"]["cdistscodi"]
        pontos.append(
            {
                "codigo": codigo,
                "nome": nome_distrito(codigo),
                "lat": round(ponto.y, 5),
                "lon": round(ponto.x, 5),
                "geometria": poligono,  # usada para fundir as zonas
            }
        )

    if not pontos:
        sys.exit("ERRO: nenhum distrito no banco. Rode antes o seed_distritos.py")

    pontos.sort(key=lambda p: p["codigo"])
    print(f"{len(pontos)} distritos, um ponto interno por distrito:")
    for p in pontos:
        print(f"  {p['nome']:<8} lat {p['lat']:>10}  lon {p['lon']:>10}")
    return pontos


def buscar(pontos, tentativas=3):
    """Uma unica requisicao para os 8 pontos (a API aceita varias coordenadas)."""
    parametros = {
        "latitude": ",".join(str(p["lat"]) for p in pontos),
        "longitude": ",".join(str(p["lon"]) for p in pontos),
        "hourly": "precipitation,temperature_2m",
        "past_days": DIAS_PASSADOS,
        "forecast_days": DIAS_PREVISAO,
        # unixtime evita ambiguidade de fuso; tudo e gravado em UTC
        "timeformat": "unixtime",
        "timezone": "GMT",
    }

    for tentativa in range(1, tentativas + 1):
        try:
            r = requests.get(URL, params=parametros, headers=HEADERS, timeout=30)
            r.raise_for_status()
            dados = r.json()
            # com varias coordenadas a API devolve lista; com uma, objeto
            return dados if isinstance(dados, list) else [dados]
        except requests.RequestException as erro:
            if tentativa == tentativas:
                raise
            espera = 2**tentativa
            print(f"  falha ({erro}); nova tentativa em {espera}s...")
            time.sleep(espera)


def conferir_grade(pontos, respostas):
    """A API encaixa cada ponto na celula mais proxima da grade do modelo.

    Se dois distritos cairem na mesma celula, recebem valores identicos -
    e a granularidade por distrito e ilusoria para eles.
    """
    celulas = {}
    for p, r in zip(pontos, respostas):
        chave = (round(r["latitude"], 3), round(r["longitude"], 3))
        celulas.setdefault(chave, []).append(p["nome"])

    print(f"\n{len(celulas)} celulas distintas da grade para {len(pontos)} distritos")

    repetidas = [nomes for nomes in celulas.values() if len(nomes) > 1]
    if repetidas:
        print("  ATENCAO: distritos na mesma celula (valores serao identicos):")
        for nomes in repetidas:
            print(f"    {', '.join(nomes)}")
    else:
        print("  OK: cada distrito tem sua propria celula.")

    return len(repetidas) == 0


def normalizar(pontos, respostas, coletado_em):
    """Uma linha por distrito por hora, marcando o que e previsao."""
    registros = []

    for p, r in zip(pontos, respostas):
        horario = r["hourly"]
        for instante, chuva, temp in zip(
            horario["time"], horario["precipitation"], horario["temperature_2m"]
        ):
            hora = datetime.fromtimestamp(instante, tz=timezone.utc)
            registros.append(
                {
                    "distrito_codigo": p["codigo"],
                    "distrito": p["nome"],
                    "hora": hora,
                    "chuva_mm": chuva,
                    "temperatura_c": temp,
                    # horas futuras sao previsao: nao podem entrar na
                    # "chuva acumulada" do painel
                    "previsao": hora > coletado_em,
                    "fonte": "open-meteo",
                    "tipo_dado": "modelo",
                    "celula_lat": r["latitude"],
                    "celula_lon": r["longitude"],
                    "coletado_em": coletado_em,
                }
            )

    return registros


def gravar(cliente, respostas, registros, coletado_em):
    banco = cliente[BANCO]

    # RAW: cada coleta e um documento proprio (historico das respostas)
    banco[COL_RAW].insert_one(
        {"fonte": "open-meteo", "coletado_em": coletado_em, "respostas": respostas}
    )
    print(f"\nRAW gravado em {BANCO}.{COL_RAW}")

    # Normalizado: upsert por (distrito, hora) - rodar de novo nao duplica,
    # e a previsao de uma hora vira valor consolidado quando a hora passa
    colecao = banco[COL]
    colecao.create_index(
        [("distrito_codigo", 1), ("hora", 1)], unique=True, name="idx_distrito_hora"
    )

    operacoes = [
        UpdateOne(
            {"distrito_codigo": r["distrito_codigo"], "hora": r["hora"]},
            {"$set": r},
            upsert=True,
        )
        for r in registros
    ]
    resultado = colecao.bulk_write(operacoes)

    print(
        f"OK: {resultado.upserted_count} horas novas, "
        f"{resultado.modified_count} atualizadas "
        f"({colecao.count_documents({})} no total em {BANCO}.{COL})"
    )


def calcular_zonas(pontos, respostas, registros, coletado_em):
    """Funde os distritos que cairam na mesma celula do modelo.

    A chuva do modelo so tem 4 valores distintos para os 8 distritos.
    Em vez de repetir o mesmo numero em varios distritos, o mapa mostra
    a zona como ela e: um poligono unico com um unico valor.

    As zonas sao recalculadas a cada coleta - se a resolucao do modelo
    mudar, os agrupamentos se ajustam sozinhos.
    """
    grupos = {}
    for p, r in zip(pontos, respostas):
        chave = (round(r["latitude"], 3), round(r["longitude"], 3))
        grupos.setdefault(chave, []).append(p)

    agora = coletado_em.timestamp()
    zonas = []

    for (lat, lon), membros in grupos.items():
        membros.sort(key=lambda m: m["codigo"])
        codigos = [m["codigo"] for m in membros]

        # dentro da mesma celula a chuva e identica: basta um distrito
        referencia = codigos[0]
        passadas = [
            r for r in registros
            if r["distrito_codigo"] == referencia and not r["previsao"]
        ]

        def chuva_desde(horas):
            inicio = agora - horas * 3600
            return round(
                sum(r["chuva_mm"] or 0.0 for r in passadas if r["hora"].timestamp() > inicio),
                1,
            )

        # a temperatura ja vem corrigida por altitude, entao essa sim
        # e propria de cada distrito
        distritos = []
        for m in membros:
            serie = [
                r for r in registros
                if r["distrito_codigo"] == m["codigo"] and not r["previsao"]
            ]
            temp = serie[-1]["temperatura_c"] if serie else None
            distritos.append({"codigo": m["codigo"], "nome": m["nome"], "temperatura_c": temp})

        # buffer(+e).buffer(-e) fecha frestas de milimetros entre
        # distritos vizinhos, que viram linhas finas dentro da zona
        e = 0.00001
        geometria = unary_union([m["geometria"] for m in membros]).buffer(e).buffer(-e)

        zonas.append(
            {
                "zona_id": "-".join(str(c) for c in codigos),
                "nome": "Zona DS " + " · ".join(ROMANOS[c - 1] for c in codigos),
                "distritos": distritos,
                "chuva_24h_mm": chuva_desde(24),
                "chuva_7d_mm": chuva_desde(24 * DIAS_PASSADOS),
                "celula_lat": lat,
                "celula_lon": lon,
                "geometria": mapping(geometria),
                # ponto garantidamente dentro da zona, para o rotulo no mapa
                "ponto_rotulo": [
                    round(geometria.representative_point().x, 5),
                    round(geometria.representative_point().y, 5),
                ],
                "fonte": "open-meteo",
                "tipo_dado": "modelo",
                "coletado_em": coletado_em,
            }
        )

    zonas.sort(key=lambda z: z["distritos"][0]["codigo"])
    return zonas


def gravar_zonas(cliente, zonas):
    """Zonas sao estado atual, nao serie historica: substitui a cada coleta."""
    colecao = cliente[BANCO][COL_ZONAS]
    colecao.drop()
    colecao.insert_many(zonas)

    print(f"\n{len(zonas)} zonas de chuva gravadas em {BANCO}.{COL_ZONAS}:")
    for z in zonas:
        print(
            f"  {z['nome']:<26} 24h {z['chuva_24h_mm']:>5} mm   "
            f"7 dias {z['chuva_7d_mm']:>6} mm"
        )


def resumo(registros, coletado_em):
    """Chuva das ultimas 24h observadas e temperatura mais recente."""
    print(f"\n{'distrito':<8}  {'chuva 24h':>10}  {'temp agora':>10}")

    inicio_24h = coletado_em.timestamp() - 24 * 3600
    por_distrito = {}
    for r in registros:
        por_distrito.setdefault(r["distrito"], []).append(r)

    for nome in sorted(por_distrito, key=lambda n: por_distrito[n][0]["distrito_codigo"]):
        passadas = [r for r in por_distrito[nome] if not r["previsao"]]
        # cada valor horario e a chuva da hora ANTERIOR: a janela e aberta
        # no inicio, senao conta 25 horas
        ultimas_24h = [r for r in passadas if r["hora"].timestamp() > inicio_24h]

        chuva = sum(r["chuva_mm"] or 0.0 for r in ultimas_24h)
        temp = passadas[-1]["temperatura_c"] if passadas else None
        temp_txt = f"{temp:.1f} °C" if temp is not None else "--"
        print(f"{nome:<8}  {chuva:>7.1f} mm  {temp_txt:>10}")


def main():
    coletado_em = datetime.now(timezone.utc)

    cliente = conectar()
    pontos = pontos_dos_distritos(cliente)

    print("\nConsultando Open-Meteo...")
    respostas = buscar(pontos)

    conferir_grade(pontos, respostas)
    registros = normalizar(pontos, respostas, coletado_em)
    gravar(cliente, respostas, registros, coletado_em)
    resumo(registros, coletado_em)

    zonas = calcular_zonas(pontos, respostas, registros, coletado_em)
    gravar_zonas(cliente, zonas)

    print(f"\nColeta de {coletado_em.isoformat()} concluida.")


if __name__ == "__main__":
    main()