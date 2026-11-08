"""Chuva x maré com o nível REAL do mar (GTSM, Copernicus): fecha a pergunta da etapa 5a.

1. Conferência: o nível total do GTSM concorda com a nossa maré calculada?
2. Ressaca: nos dias de alagamento, o mar estava mais alto que a maré prevista?
3. Mapa de calor: % de dias com alagamento na planície por chuva x nível TOTAL do mar
   (antes era com a maré calculada, sem ressaca).

Lê gold.ml_distrito_dia (chuva e alagamentos), silver.mare_gtsm_dia e silver.mare_calculada_dia.
Período: 2015-2024 (2014 fora: alvo incompleto, decisão 009).

Uso:
    python analises/ml/mare_gtsm.py
"""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from dominio import limiares  # noqa: E402
from etl.destinos import obter_destino  # noqa: E402
from ml.dados import DISTRITOS_PLANICIE  # noqa: E402

SAIDA = Path(__file__).resolve().parent / "saida"
FAIXAS = [0, limiares.CHUVA_MODERADA, limiares.CHUVA_FORTE, 30, limiares.CHUVA_MUITO_FORTE, float("inf")]
ROTULOS = ["< 8,4", "8,4–18,6", "18,6–30", "30–55,3", "≥ 55,3"]


def carregar(banco):
    gtsm = pd.DataFrame(list(banco["silver_mare_gtsm_dia"].find({}, {"_id": 0, "data": 1, "nivel_total_max_m": 1,
                                                                      "ressaca_max_m": 1})))
    calc = pd.DataFrame(list(banco["silver_mare_calculada_dia"].find({}, {"_id": 0, "data": 1, "mare_max_m": 1})))
    tabela = pd.DataFrame(list(banco["gold_ml_distrito_dia"].find(
        {"ano": {"$gte": 2015, "$lte": 2024}},
        {"_id": 0, "data": 1, "distrito_codigo": 1, "chuva_dia_mm": 1, "atendimentos_alagamento": 1})))
    if gtsm.empty or tabela.empty:
        sys.exit("faltam dados: rode python -m etl.historico.gtsm e python -m etl.derivados.ml_distrito_dia")
    for d in (gtsm, calc, tabela):
        d["dia"] = pd.to_datetime(d["data"]).dt.normalize()
    mar = gtsm.merge(calc[["dia", "mare_max_m"]], on="dia", how="left")
    return mar, tabela.merge(mar[["dia", "nivel_total_max_m", "ressaca_max_m", "mare_max_m"]], on="dia", how="left")


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    mar, df = carregar(obter_destino().banco)

    # 1. as duas fontes concordam?
    pares = mar.dropna(subset=["nivel_total_max_m", "mare_max_m"])
    corr = statistics.correlation(pares["nivel_total_max_m"], pares["mare_max_m"])
    print(f"1. Conferência ({len(pares)} dias): correlação entre o nível total do GTSM e a maré calculada = {corr:.2f}")
    print(f"   ressaca diária: mediana {mar['ressaca_max_m'].median():.3f} m | p95 {mar['ressaca_max_m'].quantile(.95):.3f} m"
          f" | máxima {mar['ressaca_max_m'].max():.3f} m")

    # 2. ressaca nos dias de alagamento (planície), comparada aos outros dias
    planicie = df[df["distrito_codigo"].isin(DISTRITOS_PLANICIE)].dropna(subset=["ressaca_max_m"])
    por_dia = planicie.groupby("dia").agg(alag=("atendimentos_alagamento", "sum"), ressaca=("ressaca_max_m", "first"),
                                          nivel=("nivel_total_max_m", "first"), chuva=("chuva_dia_mm", "max"))
    com, sem = por_dia[por_dia["alag"] > 0], por_dia[por_dia["alag"] == 0]
    chuvosos = por_dia[por_dia["chuva"] >= limiares.CHUVA_FORTE]
    print(f"\n2. Ressaca média: dias com alagamento na planície {com['ressaca'].mean():.3f} m ({len(com)} dias) | "
          f"sem alagamento {sem['ressaca'].mean():.3f} m")
    print(f"   Só dias de chuva forte (>= {limiares.CHUVA_FORTE} mm): com alagamento "
          f"{chuvosos[chuvosos['alag'] > 0]['nivel'].mean():.2f} m de nível total | sem "
          f"{chuvosos[chuvosos['alag'] == 0]['nivel'].mean():.2f} m")
    corr_r = statistics.correlation(por_dia["chuva"].fillna(0), por_dia["ressaca"], method="ranked")
    print(f"   Correlação chuva x ressaca no mesmo dia: {corr_r:+.2f} (temporal traz vento e pressão baixa junto?)")

    # 3. mapa de calor chuva x nível total, alagamento na planície
    d = planicie.dropna(subset=["chuva_dia_mm", "nivel_total_max_m"]).copy()
    d["faixa_chuva"] = pd.cut(d["chuva_dia_mm"], FAIXAS, labels=ROTULOS, right=False)
    d["faixa_mar"] = pd.qcut(d["nivel_total_max_m"], 4, labels=["baixo", "médio", "alto", "muito alto"])
    d["com_alagamento"] = d["atendimentos_alagamento"] > 0
    taxa = d.pivot_table(index="faixa_chuva", columns="faixa_mar", values="com_alagamento", aggfunc="mean", observed=False) * 100
    dias = d.pivot_table(index="faixa_chuva", columns="faixa_mar", values="com_alagamento", aggfunc="size", observed=False)
    print("\n3. % de dias com alagamento na planície (DS I, IV, V, VI) por chuva x NÍVEL TOTAL do mar (GTSM)")
    for faixa in taxa.index:
        print(f"  chuva {faixa:<9}" + "".join(f"{taxa.loc[faixa, m]:>8.1f}% ({int(dias.loc[faixa, m]):>4})" for m in taxa.columns))
    print(f"  {'mar:':<15}" + "".join(f"{m:>16}" for m in taxa.columns))

    fig, ax = plt.subplots(figsize=(8, 4.5))
    im = ax.imshow(taxa.values, cmap="Blues", aspect="auto", origin="lower")
    ax.set_xticks(range(len(taxa.columns)), taxa.columns)
    ax.set_yticks(range(len(taxa.index)), [f"{r} mm" for r in taxa.index])
    for i in range(taxa.shape[0]):
        for j in range(taxa.shape[1]):
            v = taxa.values[i, j]
            ax.text(j, i, "–" if v != v else f"{v:.0f}%", ha="center", va="center")
    ax.set_xlabel("Nível máximo do mar no dia, com ressaca (GTSM, quartis)")
    ax.set_ylabel("Chuva do dia")
    ax.set_title("Dias com alagamento na planície: chuva x nível real do mar")
    fig.colorbar(im, ax=ax, label="% dos dias")
    fig.tight_layout()
    fig.savefig(SAIDA / "mapa_calor_alagamento_nivel_gtsm.png", dpi=150)
    print(f"\nFigura: {SAIDA / 'mapa_calor_alagamento_nivel_gtsm.png'}")


if __name__ == "__main__":
    main()
