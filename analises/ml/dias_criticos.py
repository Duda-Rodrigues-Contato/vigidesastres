"""Quantos "dias críticos" cada distrito teve em 2014-2024? (CRISP-DM, fase 2)

Antes de treinar o modelo, é preciso decidir o que é um dia crítico: a partir
de quantos atendimentos REATIVOS da Defesa Civil (lonas, vistorias,
alagamentos, deslizamentos) num distrito, no mesmo dia. Esta análise mostra a
distribuição para escolher o corte, e quanto se perde de bairros sem distrito.

Lê a silver: rode antes `python -m etl bairros` (com a etapa 3a) e `defesa_civil`.

Uso:
    python analises/ml/dias_criticos.py
"""

import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dominio.distritos import nome_distrito  # noqa: E402
from etl.destinos import obter_destino  # noqa: E402

INICIO, FIM = date(2014, 1, 1), date(2024, 12, 31)
CORTES = (1, 5, 10, 20, 40)

banco = obter_destino().banco
distrito_do_bairro = {b["chave"]: b.get("distrito_codigo")
                      for b in banco["silver_bairros"].find({}, {"chave": 1, "distrito_codigo": 1})}
if not any(distrito_do_bairro.values()):
    sys.exit("silver_bairros sem distrito: aplique a etapa 3a e rode python -m etl bairros")

reativos = defaultdict(int)              # (distrito, dia) -> atendimentos reativos
sem_par, total_reativos = Counter(), 0
for d in banco["silver_defesa_civil_bairro_dia"].find({}, {"data": 1, "bairro": 1, "reativos": 1}):
    dia = d["data"].date()
    if not (INICIO <= dia <= FIM) or not d.get("reativos"):
        continue
    total_reativos += d["reativos"]
    distrito = distrito_do_bairro.get(d["bairro"])
    if distrito is None:
        sem_par[d["bairro"]] += d["reativos"]
        continue
    reativos[(distrito, dia)] += d["reativos"]

perdidos = sum(sem_par.values())
print(f"Atendimentos reativos 2014-2024: {total_reativos:,} | sem distrito: {perdidos:,} "
      f"({100 * perdidos / max(total_reativos, 1):.1f}%)".replace(",", "."))
if sem_par:
    print("  bairros da Defesa Civil sem par no IBGE (os 10 maiores):", sem_par.most_common(10))

dias = [INICIO + timedelta(n) for n in range((FIM - INICIO).days + 1)]
print(f"\n{len(dias)} dias por distrito. Valores por dia (incluindo os dias sem atendimento):")
print(f"{'distrito':<9}{'média':>7}{'p90':>6}{'p95':>6}{'p99':>6}{'máx':>6}  "
      + "".join(f"{'≥' + str(c):>8}" for c in CORTES) + "   ← % dos dias acima de cada corte")
for codigo in range(1, 9):
    serie = sorted(reativos.get((codigo, d), 0) for d in dias)
    n = len(serie)
    pct = lambda q: serie[min(n - 1, int(q * n))]
    acima = "".join(f"{100 * sum(v >= c for v in serie) / n:>7.1f}%" for c in CORTES)
    print(f"{nome_distrito(codigo):<9}{sum(serie) / n:>7.1f}{pct(.90):>6}{pct(.95):>6}{pct(.99):>6}{serie[-1]:>6}  {acima}")

print("\nMédia de reativos por dia, por mês (cidade inteira):")
por_mes = defaultdict(list)
for d in dias:
    por_mes[d.month].append(sum(reativos.get((c, d), 0) for c in range(1, 9)))
print("  " + "  ".join(f"{m:02d}:{sum(v) / len(v):.0f}" for m, v in sorted(por_mes.items())))
