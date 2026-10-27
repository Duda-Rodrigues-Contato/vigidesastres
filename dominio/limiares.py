"""
Limiares e gatilhos de alerta do Vigidesastres.

Todos os numeros que disparam alertas ficam neste arquivo, com a fonte de
cada um. Quando os limiares forem calibrados com o historico local, este e
o unico lugar a alterar (e o ponto de partida da historia US-05a).

------------------------------------------------------------------------
LIMIARES INICIAIS, DA LITERATURA. AINDA NAO CALIBRADOS COM O HISTORICO
LOCAL DE OCORRENCIAS. Aplicados a dado de MODELO (Open-Meteo), que tende a
suavizar tempestades locais intensas - os limiares da literatura foram
derivados de pluviometro.
------------------------------------------------------------------------

Fontes:
  [1] SOUZA, W. M. et al. Revista Brasileira de Geografia Fisica, v. 2,
      p. 250-268, 2012 (UFPE). Classes de chuva diaria para o Recife,
      derivadas com dados de desastres da Defesa Civil municipal (CODECIR).
      Conclusoes usadas aqui:
        - Chuva Forte e Muito Forte: "sempre ha escorregamentos e muitos
          pontos de alagamentos"
        - chuva em dias consecutivos anteriores com acumulado acima de
          30 mm agrava o dano mesmo com chuva fraca
  [2] Mare como agravante de alagamento na planicie do Recife: estudos da
      UFPE (SBRH 2025, riacho Parnamirim) e TCC de SI da UFRPE (2022).
      Nenhum estudo encontrado fixa um limiar absoluto de mare - por isso
      o criterio aqui e RELATIVO (percentil da serie recente).
"""

# ─── Classes de chuva diaria [1] ─────────────────────────────────────────
# (limite superior exclusivo, nome)
CLASSES_CHUVA = [
    (2.2, "Seco"),
    (4.2, "Chuva muito fraca"),
    (8.4, "Chuva fraca"),
    (18.6, "Chuva moderada"),
    (55.3, "Chuva forte"),
    (float("inf"), "Chuva muito forte"),
]

CHUVA_FRACA = 4.2
CHUVA_MODERADA = 8.4
CHUVA_FORTE = 18.6
CHUVA_MUITO_FORTE = 55.3

# [1] fala em "dias consecutivos anteriores" sem fixar a janela.
# 72 h e uma escolha deste projeto, a ser revista na calibracao.
JANELA_ACUMULADO_H = 72
SOLO_ENCHARCADO_MM = 30.0

# [2] criterio relativo: mare "alta" quando a maior mare cheia prevista
# para as proximas 24 h esta entre as 20% mais altas DAS MARES CHEIAS dos
# ultimos 14 dias (um ciclo de sizigia/quadratura). O percentil e sobre os
# PICOS, nao sobre todas as horas: sobre todas as horas, praticamente toda
# mare cheia passaria do limiar e o alerta dispararia duas vezes por dia.
# Sobre os picos, "alta" passa a significar as mares de sizigia.
PERCENTIL_MARE_ALTA = 80


def classificar_chuva(mm):
    if mm is None:
        return None
    for limite, nome in CLASSES_CHUVA:
        if mm < limite:
            return nome


def _mm(valor):
    return f"{valor:.1f}".replace(".", ",") + " mm"


def avaliar_gatilhos(zonas, mare):
    """Aplica as regras a cada zona de chuva.

    zonas: lista de dicts com nome, chuva_prox_24h_mm e chuva_72h_mm
    mare:  dict com alta_prevista (bool), nivel_m e quando (texto) da maior
           mare cheia prevista em 24 h - ou None se nao houver dado de mare

    Devolve alertas SUGERIDOS. Um operador confirma; o sistema nao decide.
    Cada alerta traz o motivo em texto, para ser auditavel.
    """
    alertas = []
    mare_alta = bool(mare and mare.get("alta_prevista"))

    for z in zonas:
        prev = z.get("chuva_prox_24h_mm")
        acum = z.get("chuva_72h_mm") or 0.0
        if prev is None:
            continue  # zona sem previsao: nao ha o que avaliar

        classe = classificar_chuva(prev)
        encharcado = acum >= SOLO_ENCHARCADO_MM

        # ── deslizamento (morros): chuva acumulada importa, mare nao ──
        nivel = None
        if prev >= CHUVA_MUITO_FORTE or (encharcado and prev >= CHUVA_FORTE):
            nivel = "ALTO"
        elif prev >= CHUVA_FORTE or (encharcado and prev >= CHUVA_FRACA):
            nivel = "MÉDIO"
        if nivel:
            motivo = f"Previsão de {_mm(prev)} em 24h ({classe.lower()})"
            if encharcado:
                motivo += f" com solo encharcado: {_mm(acum)} nas últimas {JANELA_ACUMULADO_H}h"
            alertas.append({"tipo": "Deslizamento", "nivel": nivel, "zona": z["nome"], "motivo": motivo})

        # ── alagamento (planicie): chuva intensa, agravada por mare alta ──
        nivel = None
        if prev >= CHUVA_MUITO_FORTE:
            nivel = "ALTO"
        elif prev >= CHUVA_FORTE:
            nivel = "ALTO" if mare_alta else "MÉDIO"
        elif prev >= CHUVA_MODERADA and mare_alta:
            nivel = "MÉDIO"
        if nivel:
            motivo = f"Previsão de {_mm(prev)} em 24h ({classe.lower()})"
            if mare_alta:
                nivel_txt = f"{mare['nivel_m']:.2f}".replace(".", ",")
                motivo += f" coincidindo com maré alta ({nivel_txt} m em {mare['quando']})"
            alertas.append({"tipo": "Alagamento", "nivel": nivel, "zona": z["nome"], "motivo": motivo})

    alertas.sort(key=lambda a: (a["nivel"] != "ALTO", a["tipo"], a["zona"]))
    return alertas
