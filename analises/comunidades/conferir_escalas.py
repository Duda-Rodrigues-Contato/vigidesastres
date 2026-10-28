"""Conferência das escalas das comunidades (CRISP-DM, fase 2: entendimento).

Os indicadores das CIS são notas de 0 a 10 sem dicionário publicado. Antes
de pintar o mapa, confere para que lado cada escala cresce, comparando as
comunidades dos bairros que o Plano de Contingência 2024 aponta com as dos
demais bairros. Lê a silver: rode antes `python -m etl comunidades`.

Uso:
    python analises/comunidades/conferir_escalas.py
"""

import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # raiz do projeto

from dominio.bairros import APELIDOS_PLANO  # noqa: E402
from etl.comum.texto import normalizar  # noqa: E402
from etl.destinos import obter_destino  # noqa: E402
from etl.fontes.areas_risco import ler_planilha  # noqa: E402


def bairros_do_plano():
    por_tipo = defaultdict(set)
    for linha in ler_planilha():
        nome = normalizar(linha["bairro"])
        por_tipo[linha["tipo"]].update(APELIDOS_PLANO.get(nome, [nome]))
    return por_tipo


def comparar(comunidades, campo, bairros_risco, rotulo):
    dentro, fora = [], []
    for c in comunidades:
        v = c["indicadores"].get(campo)
        if v is not None:
            (dentro if c["chave_bairro"] in bairros_risco else fora).append(v)

    def resumo(xs):
        if not xs:
            return "sem dados"
        acima = 100 * sum(1 for x in xs if x > 0) / len(xs)
        return f"n={len(xs):>3} | média {statistics.mean(xs):5.2f} | acima de zero {acima:3.0f}%"

    print(f"\n{rotulo} ({campo})")
    print(f"  nos bairros do plano:  {resumo(dentro)}")
    print(f"  nos demais bairros:    {resumo(fora)}")
    if len(dentro) < 2 or len(fora) < 2:
        print("  -> inconclusivo: poucas comunidades para comparar")
        return
    diferenca = statistics.mean(dentro) - statistics.mean(fora)
    espalhamento = statistics.pstdev(dentro + fora)
    # diferença pequena perto da variação natural é ruído, não confirmação
    if espalhamento == 0 or abs(diferenca) < 0.2 * espalhamento:
        print(f"  -> INCONCLUSIVO: diferença de {diferenca:+.2f} é pequena perto da variação ({espalhamento:.2f})")
    elif diferenca > 0:
        print("  -> nota ALTA = MAIS risco (coerente com o plano)")
    else:
        print("  -> ATENÇÃO: o plano aponta o contrário - a escala pode ser invertida")


def main():
    comunidades = list(obter_destino().banco["silver_comunidades"].find({}, {"geometria": 0}))
    if not comunidades:
        sys.exit("Sem comunidades na silver. Rode antes: python -m etl comunidades")
    print(f"{len(comunidades)} comunidades")

    plano = bairros_do_plano()
    comparar(comunidades, "IND_ALAGAM", plano["alagamento"], "Alagamento")
    comparar(comunidades, "DENS_ESCOR", plano["deslizamento"], "Deslizamento")

    print("\nÍndice composto por classe de precariedade (Indice_COM)")
    por_classe = defaultdict(list)
    for c in comunidades:
        v = c["indicadores"].get("Indice_COM")
        if v is not None:
            por_classe[c["precariedade"] or "?"].append(v)
    for classe, xs in sorted(por_classe.items()):
        print(f"  {classe:<40} média {statistics.mean(xs):.2f} (n={len(xs)})")

    print("\nCorrelação com o índice de alagamento (por postos, -1 a +1)")
    for campo in ["DRENAGEM", "PAVIMENTAC", "ESGOTAMENT", "Indice_COM"]:
        pares = [(c["indicadores"].get("IND_ALAGAM"), c["indicadores"].get(campo)) for c in comunidades]
        pares = [(a, b) for a, b in pares if a is not None and b is not None]
        try:
            print(f"  {campo:<11} {statistics.correlation(*zip(*pares), method='ranked'):+.2f}")
        except statistics.StatisticsError:
            print(f"  {campo:<11} sem variação suficiente")


if __name__ == "__main__":
    main()
