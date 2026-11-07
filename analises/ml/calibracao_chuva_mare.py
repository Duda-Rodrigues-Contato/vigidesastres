"""Calibração chuva x maré (etapa 5a): a partir de quanto o Recife tem problema?

1. Mapa de calor: % de dias críticos em cada combinação de chuva do dia x maré
   (todos os distritos), e % de dias com alagamento na PLANÍCIE (onde a maré pesa).
2. Árvore rasa (profundidade 3) treinada em 2015-2021 só com chuva, acumulado e
   maré: as regras dela são os limiares do Recife, legíveis.
3. Comparação no teste (2022-2024, usado uma vez): limiares atuais x árvore rasa.

Saídas: no terminal e em analises/ml/saida/ (mapa de calor em PNG e regras em texto).

Uso:
    python analises/ml/calibracao_chuva_mare.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.tree import DecisionTreeClassifier, export_text  # noqa: E402

from dominio import limiares  # noqa: E402
from etl.destinos import obter_destino  # noqa: E402
from ml import dados, linha_base, metricas  # noqa: E402

SAIDA = Path(__file__).resolve().parent / "saida"
FAIXAS_CHUVA = [0, limiares.CHUVA_MODERADA, limiares.CHUVA_FORTE, 30, limiares.CHUVA_MUITO_FORTE, float("inf")]
ROTULOS_CHUVA = ["< 8,4", "8,4–18,6", "18,6–30", "30–55,3", "≥ 55,3"]
ENTRADAS = ["chuva_dia_mm", "acumulado_72h_antes", "mare_max_m"]


def mapa_de_calor(df, coluna_alvo, titulo, arquivo):
    d = df.dropna(subset=["chuva_dia_mm", "mare_max_m"]).copy()
    d["faixa_chuva"] = pd.cut(d["chuva_dia_mm"], FAIXAS_CHUVA, labels=ROTULOS_CHUVA, right=False)
    d["faixa_mare"] = pd.qcut(d["mare_max_m"], 4, labels=["baixa", "média", "alta", "sizígia"])
    taxa = d.pivot_table(index="faixa_chuva", columns="faixa_mare", values=coluna_alvo, aggfunc="mean", observed=False) * 100
    dias = d.pivot_table(index="faixa_chuva", columns="faixa_mare", values=coluna_alvo, aggfunc="size", observed=False)
    print(f"\n{titulo} (% dos dias; entre parênteses, quantos dias)")
    for faixa in taxa.index:
        print(f"  chuva {faixa:<9}" + "".join(f"{taxa.loc[faixa, m]:>8.1f}% ({int(dias.loc[faixa, m]):>4})" for m in taxa.columns))
    print(f"  {'maré:':<15}" + "".join(f"{m:>16}" for m in taxa.columns))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    im = ax.imshow(taxa.values, cmap="Reds", aspect="auto", origin="lower")
    ax.set_xticks(range(len(taxa.columns)), taxa.columns)
    ax.set_yticks(range(len(taxa.index)), [f"{r} mm" for r in taxa.index])
    for i in range(taxa.shape[0]):
        for j in range(taxa.shape[1]):
            v = taxa.values[i, j]
            ax.text(j, i, "–" if v != v else f"{v:.0f}%", ha="center", va="center",
                    color="white" if v == v and v > taxa.values[taxa.values == taxa.values].max() / 2 else "black")
    ax.set_xlabel("Maré máxima do dia (quartis; sizígia = as 25% mais altas)")
    ax.set_ylabel("Chuva do dia")
    ax.set_title(titulo)
    fig.colorbar(im, ax=ax, label="% dos dias")
    fig.tight_layout()
    fig.savefig(SAIDA / arquivo, dpi=150)
    plt.close(fig)


def main():
    SAIDA.mkdir(exist_ok=True)
    df = dados.carregar(obter_destino().banco)
    cortes = dados.cortes_do_treino(df)
    df = dados.marcar_critico(df, cortes)
    df["dia_com_alagamento"] = df["atendimentos_alagamento"] > 0
    print("Corte de dia crítico por distrito (p95 do treino, mínimo 5):",
          {f"DS {k}": round(v) for k, v in sorted(cortes.items())})

    mapa_de_calor(df, "critico", "Dias críticos: todos os distritos", "mapa_calor_criticos.png")
    mapa_de_calor(df[df["planicie"]], "dia_com_alagamento", "Dias com alagamento: planície (DS I, IV, V, VI)",
                  "mapa_calor_alagamento_planicie.png")

    treino, teste = dados.dividir(df)
    treino = treino.dropna(subset=ENTRADAS)
    arvore = DecisionTreeClassifier(max_depth=3, class_weight="balanced", min_samples_leaf=50, random_state=42)
    arvore.fit(treino[ENTRADAS], treino["critico"])
    regras = export_text(arvore, feature_names=["chuva do dia (mm)", "acumulado 72h antes (mm)", "maré máxima (m)"],
                         class_names=["normal", "crítico"], decimals=1)
    (SAIDA / "regras_arvore_rasa.txt").write_text(regras, encoding="utf-8")
    print("\nRegras da árvore rasa (treino 2015-2021):\n" + regras)
    print("Importância das entradas:", {e: round(float(i), 2) for e, i in zip(ENTRADAS, arvore.feature_importances_)})

    print("\nTeste 2022-2024 (usado uma única vez):")
    print(metricas.texto("Limiares atuais (MÉDIO+)", metricas.resumo(teste["critico"], linha_base.prever(teste))))
    print(metricas.texto("Limiares atuais (só ALTO)", metricas.resumo(teste["critico"], linha_base.prever(teste, "ALTO"))))
    com_dado = teste.dropna(subset=ENTRADAS)
    print(metricas.texto("Árvore rasa (chuva e maré)", metricas.resumo(com_dado["critico"], arvore.predict(com_dado[ENTRADAS]))))
    print(f"\nArquivos em {SAIDA}")


if __name__ == "__main__":
    main()
