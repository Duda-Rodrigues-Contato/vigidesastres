"""Perfis de risco dos bairros: agrupamento (K-means) dos 94 bairros pelo TIPO de risco.

O índice de vulnerabilidade (4b) diz QUANTO um bairro é vulnerável; os perfis dizem DE QUE
JEITO: encosta que desliza, planície que alaga, centro com imóveis antigos, baixo risco.
Cada perfil pede uma resposta diferente (vistoria de encosta, desobstrução de canal...).

Características de cada bairro (todas por 10 mil habitantes ou proporção, em escala log):
  atendimentos da Defesa Civil 2015-2024 por tipo: deslizamento, alagamento, lona, vistoria
  eventos do REINDESC (geológicos e hidrológicos) dentro do bairro
  % da população em comunidades, risco médio das comunidades, áreas de risco, densidade

O número de grupos (3 a 6) é escolhido pela silhueta (o quanto os grupos ficam separados).
Cada grupo recebe um nome pela característica que mais o distingue da média.

  gold  gold.perfil_bairro

Uso:
    python -m ml.perfis
"""

import math
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from shapely.geometry import Point, shape
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from etl.comum.texto import normalizar
from etl.derivados.ml_distrito_dia import APELIDOS_DC
from etl.destinos import obter_destino
from etl.destinos.base import Carga

GRUPOS_TIPO = {"deslizamento": ("DESLIZ", "BARREIRA"), "alagamento": ("ALAGA", "INUNDA"), "lona": ("LONA",),
               "vistoria": ("VISTORIA", "MONITORA")}
CARACTERISTICAS = ["deslizamento_10k", "alagamento_10k", "lona_10k", "vistoria_10k", "eventos_geo_10k",
                      "eventos_hidro_10k", "pct_pop_comunidades", "risco_comunidades", "areas_risco"]
# característica -> (categoria do perfil, como aparece no nome)
ROTULOS = {"deslizamento_10k": ("encosta", "deslizamentos"), "lona_10k": ("encosta", "lonas"),
           "eventos_geo_10k": ("encosta", "eventos geológicos"), "alagamento_10k": ("planície", "alagamentos"),
           "eventos_hidro_10k": ("planície", "eventos hidrológicos"), "vistoria_10k": ("imóveis", "vistorias"),
           "pct_pop_comunidades": ("comunidades", "população em comunidades"),
           "risco_comunidades": ("comunidades", "comunidades de alto risco"),
           "areas_risco": ("áreas de risco", "áreas de risco mapeadas"), "densidade": ("comunidades", "alta densidade")}
LIMITE_PERCENTIL = 0.95   # bairros com poucos moradores inflam as taxas por 10 mil: corta no p95
MINIMO_POR_GRUPO = 3


def caracteristicas(bairros, dc, eventos, vulnerabilidade):
    """bairros {chave: {nome, populacao, area_km2, distrito_codigo, geometria}};
    dc {chave: {grupo: total}}; eventos {chave: {"Geo": n, "Hidro": n}}; vulnerabilidade {chave: {...}}."""
    linhas = []
    for chave, b in bairros.items():
        pop = b.get("populacao") or 0
        if pop < 500:
            continue
        por10k = lambda n: math.log1p(10_000 * n / pop)  # noqa: E731
        v = vulnerabilidade.get(chave, {})
        linhas.append({"chave": chave, "bairro": b["nome"], "distrito_codigo": b.get("distrito_codigo"),
                       **{f"{g}_10k": por10k(dc.get(chave, {}).get(g, 0)) for g in GRUPOS_TIPO},
                       "eventos_geo_10k": por10k(eventos.get(chave, {}).get("Geo", 0)),
                       "eventos_hidro_10k": por10k(eventos.get(chave, {}).get("Hidro", 0)),
                       "pct_pop_comunidades": v.get("pct_pop_comunidades") or 0.0,
                       "risco_comunidades": v.get("risco_comunidades") or 0.0,
                       "areas_risco": math.log1p(v.get("areas_risco") or 0),
                       "densidade": math.log1p(pop / max(b.get("area_km2") or 1, 0.1))})
    return pd.DataFrame(linhas)


def nomear(centro):
    """Nome pelas duas características que mais distinguem o grupo da média."""
    if centro.max() < 0.3:
        return "baixo risco"
    fortes = [c for c in centro.sort_values(ascending=False).index if centro[c] >= 0.3][:2]
    nome = f"{ROTULOS[fortes[0]][0]}: " + " e ".join(ROTULOS[c][1] for c in fortes)
    return nome


def agrupar(df, ks=range(3, 7), semente=42):
    valores = df[CARACTERISTICAS].clip(upper=df[CARACTERISTICAS].quantile(LIMITE_PERCENTIL), axis=1)
    x = StandardScaler().fit_transform(valores)
    candidatos = {}
    for k in ks:
        r = KMeans(k, n_init=20, random_state=semente).fit_predict(x)
        if np.bincount(r).min() >= MINIMO_POR_GRUPO:            # nenhum grupo de 1 ou 2 bairros
            candidatos[k] = silhouette_score(x, r)
    melhor = max(candidatos, key=candidatos.get) if candidatos else min(ks)
    km = KMeans(melhor, n_init=20, random_state=semente).fit(x)
    rotulos = km.labels_.copy()
    # garantia: bairro isolado (grupo com menos de 3) vai para o grupo grande mais parecido
    grandes = [g for g in range(melhor) if (rotulos == g).sum() >= MINIMO_POR_GRUPO]
    for i in np.flatnonzero(~np.isin(rotulos, grandes)):
        rotulos[i] = min(grandes, key=lambda g: np.linalg.norm(x[i] - km.cluster_centers_[g]))
    rotulos = np.unique(rotulos, return_inverse=True)[1]
    melhor = int(rotulos.max()) + 1
    df = df.assign(grupo=rotulos)
    centros = pd.DataFrame([x[rotulos == g].mean(axis=0) for g in range(melhor)], columns=CARACTERISTICAS)
    nomes, usados = {}, defaultdict(int)
    for g, c in centros.iterrows():
        nome = nomear(c)
        usados[nome] += 1
        nomes[g] = nome if usados[nome] == 1 else f"{nome} ({usados[nome]})"
    df["perfil"] = df["grupo"].map(nomes)
    return df, melhor, silhouette_score(x, rotulos), centros.rename(index=nomes)


def ler(banco):
    bairros = {b["chave"]: b for b in banco["silver_bairros"].find()}
    dc = defaultdict(lambda: defaultdict(int))
    for d in banco["silver_defesa_civil_bairro_dia"].find({"ano": {"$gte": 2015, "$lte": 2024}},
                                                          {"bairro": 1, "por_tipo": 1, "por_ocorrencia": 1}):
        chave = APELIDOS_DC.get(normalizar(d["bairro"]), normalizar(d["bairro"]))
        for tipo, n in list((d.get("por_tipo") or {}).items()) + list((d.get("por_ocorrencia") or {}).items()):
            for g, termos in GRUPOS_TIPO.items():
                if any(t in tipo for t in termos):
                    dc[chave][g] += n
    formas = {k: shape(b["geometria"]) for k, b in bairros.items() if b.get("geometria")}
    eventos = defaultdict(lambda: defaultdict(int))
    for o in banco["silver_reindesc_ocorrencias"].find({"unidade": {"$regex": "^DS "}}):
        if o.get("latitude") is None:
            continue
        p = Point(o["longitude"], o["latitude"])
        chave = next((k for k, f in formas.items() if f.contains(p)), None)
        if chave:
            eventos[chave][o.get("tipologia")] += 1
    vul = {v["chave"]: v for v in banco["gold_vulnerabilidade_bairro"].find()}
    return bairros, dc, eventos, vul


def carregar(destino, avisar=print):
    df = caracteristicas(*ler(destino.banco))
    df, k, silhueta, centros = agrupar(df)
    agora = datetime.now(timezone.utc)
    linhas = [{**{c: (float(v) if isinstance(v, (float, np.floating)) else v) for c, v in r.items()},
               "grupo": int(r["grupo"]), "coletado_em": agora} for r in df.to_dict("records")]
    destino.carregar(Carga("gold.perfil_bairro", linhas, chaves=("chave",)))
    avisar(f"{len(df)} bairros em {k} perfis (silhueta {silhueta:.2f}; acima de 0,25 os grupos são razoavelmente separados;"
           f" taxas cortadas no p{int(LIMITE_PERCENTIL * 100)}, mínimo de {MINIMO_POR_GRUPO} bairros por grupo)")
    for nome, g in df.groupby("perfil"):
        avisar(f"  {nome:<34} {len(g):>2} bairros: {', '.join(g.sort_values('bairro')['bairro'].head(6))}"
               + (" ..." if len(g) > 6 else ""))
    avisar("\nCentro de cada perfil (desvios em relação à média dos bairros):")
    avisar(centros.round(1).to_string())


def main():
    from pathlib import Path
    saida = Path(__file__).resolve().parents[1] / "analises" / "ml" / "saida"
    saida.mkdir(parents=True, exist_ok=True)
    linhas = []
    carregar(obter_destino(), avisar=lambda t: (print(t, flush=True), linhas.append(t)))
    (saida / "resultado_perfis.txt").write_text("\n".join(linhas), encoding="utf-8")


if __name__ == "__main__":
    main()
