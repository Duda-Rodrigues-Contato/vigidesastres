"""Calendário de risco: em que época do ano cada distrito mais precisa de equipe (etapa 4a).

A partir dos atendimentos REATIVOS da Defesa Civil (2014-2024), por distrito e dia:
  - média de atendimentos por dia em cada mês, e quanto isso é acima da média do distrito (índice)
  - período crítico: os meses seguidos com índice >= 1,5 (50% acima da média do próprio distrito)
  - semana de pico: a semana do ano com mais atendimentos (média móvel de 3 semanas)
  - variação entre os anos: em cada mês, o ano mais calmo e o mais intenso

  gold  gold.calendario_risco_mes        distrito x mês
  gold  gold.calendario_risco_distrito   resumo por distrito (código 0 = Recife inteiro)

Uso:
    python -m etl.derivados.calendario
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from dominio.distritos import nome_distrito
from etl.destinos import obter_destino
from etl.destinos.base import Carga

INICIO, FIM = date(2014, 1, 1), date(2024, 12, 31)
LIMIAR_CRITICO = 1.5
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
CIDADE = 0


def _semana(d):
    """Semana do ano de 0 a 51 (a 53ª, de 1 ou 2 dias, entra na 52ª)."""
    return min((d.timetuple().tm_yday - 1) // 7, 51)


def periodo_critico(indices):
    """A maior sequência de meses seguidos (dez -> jan conta) com índice >= limiar. [] se nenhum."""
    melhor, atual = [], []
    for m in list(range(12)) * 2:
        if indices[m] >= LIMIAR_CRITICO:
            atual.append(m)
            if len(atual) > len(melhor) and len(atual) <= 12:
                melhor = list(atual)
        else:
            atual = []
    return [m + 1 for m in melhor]


def texto_periodo(meses):
    if not meses:
        return "sem período marcadamente acima da média"
    if len(meses) == 1:
        return MESES[meses[0] - 1]
    return f"{MESES[meses[0] - 1]} a {MESES[meses[-1] - 1]}"


def calcular(totais, inicio=INICIO, fim=FIM):
    """totais: {(distrito, date): atendimentos}. Devolve (linhas_mes, linhas_distrito)."""
    dias = [inicio + timedelta(n) for n in range((fim - inicio).days + 1)]
    distritos = sorted({d for d, _ in totais} | {CIDADE})
    linhas_mes, linhas_distrito = [], []
    for codigo in distritos:
        if codigo == CIDADE:
            por_dia = defaultdict(int)
            for (c, d), v in totais.items():
                por_dia[d] += v
        else:
            por_dia = {d: v for (c, d), v in totais.items() if c == codigo}
        media_anual = sum(por_dia.get(d, 0) for d in dias) / len(dias)

        por_mes, por_mes_ano, por_semana = defaultdict(list), defaultdict(list), defaultdict(list)
        for d in dias:
            v = por_dia.get(d, 0)
            por_mes[d.month].append(v)
            por_mes_ano[(d.month, d.year)].append(v)
            por_semana[_semana(d)].append(v)

        indices = []
        for mes in range(1, 13):
            media = sum(por_mes[mes]) / len(por_mes[mes])
            indice = media / media_anual if media_anual else 0.0
            indices.append(indice)
            anos = {ano: sum(v) / len(v) for (m, ano), v in por_mes_ano.items() if m == mes}
            calmo, intenso = min(anos, key=anos.get), max(anos, key=anos.get)
            linhas_mes.append({"distrito_codigo": codigo, "distrito": nome_distrito(codigo) if codigo else "Recife",
                               "mes": mes, "media_dia": round(media, 2), "indice": round(indice, 2),
                               "ano_calmo": calmo, "media_ano_calmo": round(anos[calmo], 2),
                               "ano_intenso": intenso, "media_ano_intenso": round(anos[intenso], 2)})

        semanas = [sum(por_semana[w]) / len(por_semana[w]) for w in range(52)]
        suave = [(semanas[w - 1] + semanas[w] + semanas[(w + 1) % 52]) / 3 for w in range(52)]
        pico = max(range(52), key=lambda w: suave[w])
        inicio_pico = date(2021, 1, 1) + timedelta(weeks=pico)
        meses_criticos = periodo_critico(indices)
        linhas_distrito.append({
            "distrito_codigo": codigo, "distrito": nome_distrito(codigo) if codigo else "Recife",
            "media_anual_dia": round(media_anual, 2),
            "meses_criticos": meses_criticos, "periodo_critico": texto_periodo(meses_criticos),
            "semana_pico": pico + 1,
            "pico_texto": f"{inicio_pico:%d/%m} a {inicio_pico + timedelta(days=6):%d/%m}",
            "media_semana_pico": round(suave[pico], 1),
        })
    return linhas_mes, linhas_distrito


def totais_da_defesa_civil(banco, inicio=INICIO, fim=FIM):
    """{(distrito, date): reativos}, juntando a silver da Defesa Civil com o distrito de cada bairro."""
    distrito_do_bairro = {b["chave"]: b.get("distrito_codigo")
                          for b in banco["silver_bairros"].find({}, {"chave": 1, "distrito_codigo": 1})}
    if not any(distrito_do_bairro.values()):
        raise ValueError("silver_bairros sem distrito: rode antes python -m etl bairros (etapa 3a)")
    totais = defaultdict(int)
    for d in banco["silver_defesa_civil_bairro_dia"].find({}, {"data": 1, "bairro": 1, "reativos": 1}):
        dia, distrito = d["data"].date(), distrito_do_bairro.get(d["bairro"])
        if distrito and inicio <= dia <= fim and d.get("reativos"):
            totais[(distrito, dia)] += d["reativos"]
    return totais


def carregar(destino, avisar=print):
    linhas_mes, linhas_distrito = calcular(totais_da_defesa_civil(destino.banco))
    agora = datetime.now(timezone.utc)
    for l in linhas_mes + linhas_distrito:
        l["coletado_em"] = agora
    destino.carregar(Carga("gold.calendario_risco_mes", linhas_mes, chaves=("distrito_codigo", "mes")))
    destino.carregar(Carga("gold.calendario_risco_distrito", linhas_distrito, chaves=("distrito_codigo",)))
    for l in linhas_distrito:
        avisar(f"  {l['distrito']:<8} período crítico: {l['periodo_critico']:<22} "
               f"pico: semana {l['semana_pico']} ({l['pico_texto']})  média {l['media_anual_dia']}/dia")


if __name__ == "__main__":
    carregar(obter_destino())
