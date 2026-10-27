"""
Inspeção das fontes do portal do Recife antes de montar as camadas.

Mostra SÓ distribuições e contagens: nenhum endereço, nenhum registro
individual (o arquivo da Defesa Civil tem endereço de quem pediu ajuda).

Uso:
    pip install ftfy
    python scripts/inspecionar_fontes.py
"""

import csv
import io
import statistics
from collections import Counter

import requests
from ftfy import fix_text

API = "https://dados.recife.pe.gov.br/api/3/action"
H = {"User-Agent": "Vigidesastres/0.1"}


def pacote(termo, trecho):
    res = requests.get(
        f"{API}/package_search", params={"q": termo, "rows": 20}, headers=H, timeout=60
    ).json()["result"]["results"]
    return next((p for p in res if trecho in p["title"].lower()), None)


def comunidades():
    """Faixa de valores dos indicadores de cada comunidade."""
    p = pacote("favelas", "favelas")
    geo = requests.get(p["resources"][0]["url"], headers=H, timeout=120).json()
    print("== COMUNIDADES:", len(geo["features"]))
    campos = ["IND_ALAGAM", "DRENAGEM", "DENS_ESCOR", "Precarieda", "Prioritari",
              "Populacao_", "ZEIS", "Ano", "Indice_COM"]
    for campo in campos:
        valores = [f["properties"].get(campo) for f in geo["features"]]
        numeros = [x for x in valores if isinstance(x, (int, float))]
        if numeros and len(set(numeros)) > 6:
            print(f"  {campo:<11} numérico | min {min(numeros)} | "
                  f"mediana {statistics.median(numeros)} | max {max(numeros)} | "
                  f"vazios {len(valores) - len(numeros)}")
        else:
            print(f"  {campo:<11} valores: {Counter(valores).most_common(6)}")


def defesa_civil():
    """Categorias e formato da data, em 2024."""
    p = pacote("Defesa Civil", "atendimentos da defesa civil")
    recurso = next(r for r in p["resources"] if "2024" in r["name"])
    print("\n== DEFESA CIVIL 2024: baixando (arquivo grande)...")
    bruto = requests.get(recurso["url"], headers=H, timeout=300).content
    texto = fix_text(bruto.decode("utf-8", "replace"))
    cabecalho = texto.splitlines()[0]
    sep = ";" if cabecalho.count(";") > cabecalho.count(",") else ","
    linhas = list(csv.DictReader(io.StringIO(texto), delimiter=sep))

    print(f"  {len(linhas)} atendimentos")
    print("  exemplos de Data:", [l["Data"] for l in linhas[:3]])
    for campo in ["Ocorrencia", "Solicitacao", "Tipo_da_Acao", "Grau_de_Risco", "Regional"]:
        print(f"  {campo}: {Counter(l[campo] for l in linhas).most_common(8)}")
    sem_bairro = sum(1 for l in linhas if not l["Bairro"].strip())
    distintos = len({l["Bairro"].strip() for l in linhas})
    print(f"  sem bairro: {sem_bairro} | bairros distintos: {distintos}")


def cras():
    p = pacote("CRAS", "assistência social")
    print("\n== CRAS:", p["title"] if p else "não encontrado")
    if p:
        for r in p["resources"]:
            print("  -", r.get("name"), f"[{r.get('format')}]")


if __name__ == "__main__":
    comunidades()
    defesa_civil()
    cras()