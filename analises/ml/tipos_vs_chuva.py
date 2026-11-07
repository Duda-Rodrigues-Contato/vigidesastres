"""Quais atendimentos da Defesa Civil acompanham a chuva, em cada distrito? (decisão 009, ajuste 2)

Para cada distrito e grupo de atendimento, a correlação (por postos, de -1 a +1)
entre a quantidade de atendimentos no dia e a chuva acumulada em 3 dias.
Se as VISTORIAS de um distrito acompanham a chuva tanto quanto as lonas, elas
deveriam entrar no alvo daquele distrito.

Lê gold.ml_distrito_dia (rode antes python -m etl.derivados.ml_distrito_dia).

Uso:
    python analises/ml/tipos_vs_chuva.py
"""

import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dominio.distritos import nome_distrito  # noqa: E402
from etl.comum.texto import normalizar  # noqa: E402
from etl.derivados.ml_distrito_dia import APELIDOS_DC  # noqa: E402
from etl.destinos import obter_destino  # noqa: E402

GRUPOS = {"lona": ("LONA",), "alagamento": ("ALAGA", "INUNDA"), "deslizamento": ("DESLIZ", "BARREIRA"),
          "vistoria": ("VISTORIA",), "monitoramento": ("MONITORA",)}

banco = obter_destino().banco
chuva3d = {(l["distrito_codigo"], l["data"].date()): l["chuva_3d_mm"]
           for l in banco["gold_ml_distrito_dia"].find({}, {"distrito_codigo": 1, "data": 1, "chuva_3d_mm": 1})}
if not chuva3d:
    sys.exit("gold_ml_distrito_dia vazia: rode antes python -m etl.derivados.ml_distrito_dia")
distrito_do_bairro = {b["chave"]: b.get("distrito_codigo") for b in banco["silver_bairros"].find({}, {"chave": 1, "distrito_codigo": 1})}

contagem = defaultdict(int)  # (distrito, dia, grupo) -> atendimentos
for d in banco["silver_defesa_civil_bairro_dia"].find({}, {"data": 1, "bairro": 1, "por_tipo": 1, "por_ocorrencia": 1}):
    bairro = normalizar(d["bairro"])
    distrito = distrito_do_bairro.get(APELIDOS_DC.get(bairro, bairro))
    if not distrito:
        continue
    for tipo, n in list((d.get("por_tipo") or {}).items()) + list((d.get("por_ocorrencia") or {}).items()):
        for grupo, termos in GRUPOS.items():
            if any(t in tipo for t in termos):
                contagem[(distrito, d["data"].date(), grupo)] += n

print(f"{'distrito':<9}" + "".join(f"{g:>15}" for g in GRUPOS) + "   (correlação com a chuva de 3 dias)")
for distrito in range(1, 9):
    dias = [dia for (c, dia), v in chuva3d.items() if c == distrito and v is not None]
    linha = f"{nome_distrito(distrito):<9}"
    for grupo in GRUPOS:
        x = [chuva3d[(distrito, dia)] for dia in dias]
        y = [contagem.get((distrito, dia, grupo), 0) for dia in dias]
        try:
            linha += f"{statistics.correlation(x, y, method='ranked'):>15.2f}"
        except statistics.StatisticsError:
            linha += f"{'-':>15}"
    print(linha)
print("\nLeitura: acima de ~0,3 o grupo acompanha a chuva; perto de 0, não tem relação com ela.")
