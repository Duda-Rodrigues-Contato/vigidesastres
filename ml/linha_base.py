"""Linha de base: os gatilhos atuais (limiares da literatura) aplicados ao histórico.

Usa a MESMA função do sistema (dominio.limiares.avaliar_gatilhos), dia a dia, como
se a chuva do dia fosse a previsão de 24 h e os 3 dias anteriores o acumulado.
É a régua que o modelo precisa vencer.
"""

from dominio.limiares import avaliar_gatilhos


def gatilho_atual(linha):
    """'ALTO', 'MÉDIO' ou None para uma linha da tabela (distrito x dia)."""
    if linha["chuva_dia_mm"] is None or linha["chuva_dia_mm"] != linha["chuva_dia_mm"]:  # None ou NaN
        return None
    acum = linha["acumulado_72h_antes"]
    zona = {"nome": "x", "chuva_prox_24h_mm": float(linha["chuva_dia_mm"]),
            "chuva_72h_mm": 0.0 if acum != acum or acum is None else float(acum)}
    mare = {"alta_prevista": bool(linha["mare_alta"]), "nivel_m": float(linha["mare_max_m"] or 0), "quando": "-"}
    alertas = avaliar_gatilhos([zona], mare)
    if any(a["nivel"] == "ALTO" for a in alertas):
        return "ALTO"
    return "MÉDIO" if alertas else None


def prever(df, nivel_minimo="MÉDIO"):
    """Série booleana: a linha de base alertaria? (MÉDIO ou mais, por padrão)."""
    niveis = df.apply(gatilho_atual, axis=1)
    return niveis.isin(["ALTO"]) if nivel_minimo == "ALTO" else niveis.notna()
