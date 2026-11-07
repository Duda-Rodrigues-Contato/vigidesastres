"""Histórico semanal de arboviroses no Recife, 2014 até hoje (etapa 3d do ML).

Usa o mesmo conector do dia a dia (etl/fontes/infodengue.py), que busca dois
anos por vez (o ano pedido e o anterior), e o roda para anos alternados até
cobrir o período inteiro. O upsert por (doença, semana) não duplica nada,
e o gold semanal é recalculado com a comparação "mesma semana do ano anterior".

Serve para a análise chuva -> dengue (etapa 4c): os casos por semana da
cidade inteira, desde 2014. Leva poucos minutos (uma requisição por doença e
par de anos).

Uso:
    python -m etl.historico.infodengue
"""

import argparse
from datetime import datetime, timezone

from etl.destinos import obter_destino
from etl.fontes.infodengue import InfoDengue


def carregar(destino, inicio, fim, avisar=print):
    # o conector busca (ano - 1, ano): anos alternados a partir de inicio + 1 cobrem tudo
    anos = list(range(inicio + 1, fim + 1, 2))
    if not anos or anos[-1] < fim:
        anos.append(fim)
    for ano in anos:
        r = InfoDengue(destino, ano=ano).executar()
        avisar(f"  {ano - 1}-{ano}: {r['status']}" + (f" | {r.get('erro')}" if r["status"] != "ok" else ""))


def main():
    p = argparse.ArgumentParser(description="Histórico semanal do InfoDengue (dengue, chikungunya, zika).")
    p.add_argument("--inicio", type=int, default=2014)
    p.add_argument("--fim", type=int, default=datetime.now(timezone.utc).year)
    a = p.parse_args()
    carregar(obter_destino(), a.inicio, a.fim, avisar=lambda s: print(s, flush=True))
    banco = obter_destino().banco
    for doenca in ("dengue", "chikungunya", "zika"):
        anos = sorted(banco["silver_arbovirose_semanal"].distinct("ano", {"doenca": doenca}))
        print(f"{doenca}: {banco['silver_arbovirose_semanal'].count_documents({'doenca': doenca})} semanas, "
              f"de {anos[0] if anos else '-'} a {anos[-1] if anos else '-'}")


if __name__ == "__main__":
    main()
