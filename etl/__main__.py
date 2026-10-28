"""Orquestrador do ETL.

    python -m etl                       todas as fontes
    python -m etl infodengue            só uma
    python -m etl --frequencia diaria   só as que mudam todo dia
    python -m etl --listar              mostra as fontes registradas

Uma fonte que falha não interrompe as outras: o erro fica registrado em
etl_execucoes e o processo segue. O código de saída é 1 se alguma falhou,
para um agendador saber que precisa avisar alguém.
"""

import argparse
import sys

from etl.destinos import obter_destino
from etl.fontes.areas_risco import AreasRisco
from etl.fontes.avisos_inmet import AvisosInmet
from etl.fontes.cemaden import Cemaden
from etl.fontes.cnes import Cnes
from etl.fontes.comunidades import Comunidades
from etl.fontes.defesa_civil import DefesaCivil
from etl.fontes.distritos import Distritos
from etl.fontes.infodengue import InfoDengue
from etl.fontes.mare import Mare
from etl.fontes.previsao import Previsao
from etl.fontes.rede_apoio import RedeApoio

# Registro das fontes já migradas para o padrão novo. As demais ainda
# rodam pelos scripts antigos em scripts/ até serem migradas.
FONTES = {c.nome: c for c in [InfoDengue, DefesaCivil, Distritos, AreasRisco, Comunidades, RedeApoio, Cnes, Mare, Cemaden, AvisosInmet, Previsao]}

def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m etl", description="ETL do Vigidesastres")
    parser.add_argument("fontes", nargs="*", help="nomes das fontes (padrão: todas)")
    parser.add_argument("--frequencia", choices=["diaria", "semanal", "anual"])
    parser.add_argument("--listar", action="store_true")
    args = parser.parse_args(argv)

    if args.listar:
        for nome, classe in FONTES.items():
            print(f"{nome:<14} {classe.frequencia:<8} {classe.descricao}")
        return 0

    desconhecidas = set(args.fontes) - set(FONTES)
    if desconhecidas:
        parser.error(f"fonte(s) desconhecida(s): {', '.join(sorted(desconhecidas))}")

    escolhidas = [FONTES[n] for n in (args.fontes or FONTES)]
    if args.frequencia:
        escolhidas = [c for c in escolhidas if c.frequencia == args.frequencia]
    if not escolhidas:
        print("Nenhuma fonte para executar.")
        return 0

    destino = obter_destino()
    resultados = [classe(destino).executar() for classe in escolhidas]

    falhas = [r["fonte"] for r in resultados if r["status"] != "ok"]
    print(f"\n{len(resultados) - len(falhas)} de {len(resultados)} fontes concluídas"
          + (f" | falharam: {', '.join(falhas)}" if falhas else ""))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
