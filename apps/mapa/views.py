"""Mapa e APIs GeoJSON que ele consome."""

from apps.painel.situacao import situacao_por_distrito

from django.http import JsonResponse
from django.shortcuts import redirect, render
from apps.fontes import painel_chuva
from apps.fontes.repositorios import arboviroses as repo_arboviroses
from apps.fontes.repositorios import referencia as repo_referencia


def mapa_view(request):
    return render(request, "mapa/mapa.html")


def get_distritos_geojson(request):
    """Distritos sanitários do Recife (8, desde a reorganização de 2014).

    O GeoJSON do portal da prefeitura traz apenas o campo numérico
    `cdistscodi` (1 a 8); a conversão para "DS I"..."DS VIII" é feita
    no front-end.
    """
    features = repo_referencia.distritos_features()
    return JsonResponse({"type": "FeatureCollection", "features": features})


def get_unidades_geojson(request):
    """Unidades de saúde como GeoJSON, prontas para o Leaflet.

    Aceita ?tipo=2 (ou repetido) para filtrar por código de tipo CNES.
    Unidades sem coordenada ficam de fora: quebrariam a camada do mapa.
    """
    try:
        tipos = [int(t) for t in request.GET.getlist("tipo")]
    except ValueError:
        return JsonResponse({"erro": "parâmetro 'tipo' deve ser numérico"}, status=400)

    features = [
        {
            "type": "Feature",
            "geometry": u["localizacao"],
            "properties": {
                "nome": u.get("nome"),
                "tipo": u.get("tipo"),
                "codigo_tipo": u.get("codigo_tipo"),
                "bairro": u.get("bairro"),
                "turno": u.get("turno"),
            },
        }
        for u in repo_referencia.unidades_saude(tipos)
    ]

    return JsonResponse({"type": "FeatureCollection", "features": features})


def get_chuva_distritos_geojson(request):
    """Distritos coloridos pela chuva medida em 24 h (pior pluviômetro do distrito)."""
    return JsonResponse(painel_chuva.chuva_por_distrito_geojson(repo_referencia.distritos_features()))


def get_estacoes_chuva_geojson(request):
    """Pluviômetros do CEMADEN como pontos, com a chuva das últimas 24 h."""
    return JsonResponse(painel_chuva.estacoes_geojson())


def get_areas_risco_geojson(request):
    """Bairros que contêm áreas de risco alto ou muito alto (R3/R4).

    Fonte: Plano de Contingência 2024 da Defesa Civil do Recife. O plano
    identifica comunidades DENTRO dos bairros; o bairro na camada indica que
    ele contém essas áreas, não que esteja todo em risco.
    """
    features = [
        {
            "type": "Feature",
            "geometry": a["geometria"],
            "properties": {
                "bairro": a["bairro"],
                "tipos": a["tipos"],
                "alagamento": a["alagamento"],
                "deslizamento": a["deslizamento"],
                "total_areas": a["total_areas"],
                "nivel": a["nivel"],
                "fonte": a["fonte"],
            },
        }
        for a in repo_referencia.areas_risco()
    ]
    return JsonResponse({"type": "FeatureCollection", "features": features})


DOENCAS_ARBO = ("dengue", "chikungunya", "zika")


def get_arboviroses_bairros_geojson(request):
    """Casos prováveis e incidência por bairro, num ano. Histórico: o arquivo
    mais recente da prefeitura é de 2025; a semana atual vem do InfoDengue.

    ?ano=2025 (padrão: o mais recente)  ?doenca=dengue|chikungunya|zika|todas
    """
    anos = repo_arboviroses.anos_por_bairro()
    if not anos:
        return JsonResponse({"type": "FeatureCollection", "features": [], "anos": []})

    try:
        ano = int(request.GET.get("ano", anos[-1]))
    except ValueError:
        return JsonResponse({"erro": "ano inválido"}, status=400)
    doenca = request.GET.get("doenca", "todas")
    doencas = DOENCAS_ARBO if doenca == "todas" else (doenca,)
    if not set(doencas) <= set(DOENCAS_ARBO):
        return JsonResponse({"erro": "doença inválida"}, status=400)

    por_bairro = {}
    for r in repo_arboviroses.por_bairro(ano, doencas):
        b = por_bairro.setdefault(r["chave"], {"populacao": r["populacao"], "por_doenca": {}})
        b["por_doenca"][r["doenca"]] = r["provaveis"]

    features = []
    for bairro in repo_referencia.bairros():
        dados = por_bairro.get(bairro["chave"])
        if not dados:
            continue
        provaveis = sum(dados["por_doenca"].values())
        populacao = dados["populacao"]
        features.append({
            "type": "Feature",
            "geometry": bairro["geometria"],
            "properties": {
                "bairro": bairro["nome"],
                "populacao": populacao,
                "provaveis": provaveis,
                "por_doenca": dados["por_doenca"],
                "incidencia_10k": round(provaveis / populacao * 10_000, 1) if populacao else None,
            },
        })

    return JsonResponse({
        "type": "FeatureCollection",
        "ano": ano, "anos": anos, "doenca": doenca,
        "fonte": "SINAN, via Portal de Dados Abertos do Recife; população: IBGE, Censo 2022",
        "features": features,
    })


def get_arboviroses_resumo(request):
    """Situação da semana na cidade (InfoDengue), para o painel do mapa."""
    resumo = repo_arboviroses.resumo_semana_cidade()
    return JsonResponse({"resumo": resumo})


INDICADORES_COMUNIDADE = {"alagamento": "IND_ALAGAM", "deslizamento": "DENS_ESCOR", "indice": "Indice_COM"}


def get_comunidades_geojson(request):
    """Comunidades de Interesse Social (levantamento de 2014).

    ?indicador=alagamento|deslizamento|indice. Notas de 0 a 10; maior = pior,
    conferido contra o Plano de Contingência 2024 (analises/comunidades/conferir_escalas.py).
    """
    campo = INDICADORES_COMUNIDADE.get(request.GET.get("indicador", "alagamento"))
    if not campo:
        return JsonResponse({"erro": "indicador inválido"}, status=400)
    features = [
        {
            "type": "Feature",
            "geometry": c["geometria"],
            "properties": {
                "nome": c["nome"], "bairro": c["bairro"],
                "populacao_2014": c.get("populacao_2014"), "precariedade": c.get("precariedade"),
                "valor": c["indicadores"].get(campo), "indicadores": c["indicadores"],
            },
        }
        for c in repo_referencia.comunidades()
    ]
    return JsonResponse({"type": "FeatureCollection", "features": features})


TIPOS_REDE = ("abrigo", "escola", "cras")


def get_rede_apoio_geojson(request):
    """Abrigos, escolas e CRAS como pontos. ?tipo=abrigo|escola|cras (opcional)."""
    tipo = request.GET.get("tipo")
    if tipo and tipo not in TIPOS_REDE:
        return JsonResponse({"erro": "tipo inválido"}, status=400)
    features = [
        {
            "type": "Feature",
            "geometry": p["localizacao"],
            "properties": {
                "tipo": p["tipo"],
                "nome": p["nome"],
                "bairro": p["bairro"],
                "endereco": p["endereco"],
                "detalhe": p.get("detalhe", {}),
                "fonte": p["fonte"],
            },
        }
        for p in repo_referencia.rede_apoio(tipo)
    ]
    return JsonResponse({"type": "FeatureCollection", "features": features})


def get_situacao_distritos(request):
    """Nível de cada distrito (gatilhos reais), chuva, previsão e alertas abertos."""
    return JsonResponse({"distritos": situacao_por_distrito()})
