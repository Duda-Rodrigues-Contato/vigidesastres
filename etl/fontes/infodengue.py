"""InfoDengue - dengue, chikungunya e zika no Recife, por semana.

Fonte: InfoDengue (Fiocruz + FGV), API aberta. Casos vêm do SINAN.

  bronze  bronze_infodengue                 resposta da API, por doença
  silver  silver.arbovirose_semanal         uma linha por doença e semana
  gold    gold.arbovirose_semana_cidade     as três doenças somadas, por semana

O InfoDengue corrige o atraso de notificação (casos_est). A semana mais
recente sempre parece quase vazia, porque as fichas ainda estão chegando.

Limites: municipal (o Recife inteiro) e semanal.
"""

from datetime import datetime, timedelta, timezone

from dominio.arboviroses import DOENCAS, nome_do_nivel
from etl.base import Conector
from etl.comum.http import get_json
from etl.destinos.base import Carga

URL = "https://info.dengue.mat.br/api/alertcity"
GEOCODE_RECIFE = 2611606  # IBGE com dígito verificador


def _inicio_semana(valor):
    """data_iniSE vem em milissegundos no JSON (texto 'AAAA-MM-DD' no CSV)."""
    if isinstance(valor, (int, float)):
        return datetime.fromtimestamp(valor / 1000, tz=timezone.utc)
    return datetime.fromisoformat(str(valor)[:10]).replace(tzinfo=timezone.utc)


class InfoDengue(Conector):
    nome = "infodengue"
    frequencia = "semanal"
    descricao = "Arboviroses no Recife por semana epidemiológica (InfoDengue)"

    def __init__(self, destino, ano=None):
        super().__init__(destino)
        self.ano = ano or datetime.now(timezone.utc).year

    def extrair(self):
        """O ano atual e o anterior (para comparar com a mesma semana)."""
        bruto = {}
        for doenca in DOENCAS:
            dados = get_json(URL, {
                "geocode": GEOCODE_RECIFE, "disease": doenca, "format": "json",
                "ew_start": 1, "ew_end": 53, "ey_start": self.ano - 1, "ey_end": self.ano,
            })
            if not isinstance(dados, list):
                raise ValueError(f"resposta inesperada para {doenca}: {str(dados)[:200]}")
            bruto[doenca] = dados
        return bruto

    def documentos_bronze(self, bruto):
        return [{"doenca": d, "registros": regs} for d, regs in bruto.items()]

    def transformar(self, bruto, coletado_em):
        linhas = []
        for doenca, registros in bruto.items():
            for r in registros:
                se = int(r["SE"])
                linhas.append({
                    "doenca": doenca,
                    "se": se,  # AAAASS: 202640 = semana 40 de 2026
                    "ano": se // 100,
                    "semana": se % 100,
                    "inicio_semana": _inicio_semana(r["data_iniSE"]),
                    "casos": r.get("casos"),
                    "casos_est": r.get("casos_est"),
                    "casos_est_min": r.get("casos_est_min"),
                    "casos_est_max": r.get("casos_est_max"),
                    "nivel": r.get("nivel"),
                    "rt": r.get("Rt"),
                    "p_rt1": r.get("p_rt1"),
                    "incidencia_100k": r.get("p_inc100k"),
                    "receptivo": r.get("receptivo"),
                    "transmissao": r.get("transmissao"),
                    "populacao": r.get("pop"),
                    "notificados_no_ano": r.get("notif_accum_year"),
                    "versao_modelo": r.get("versao_modelo"),
                    "coletado_em": coletado_em,
                })
        # as estimativas das semanas recentes são revistas toda semana:
        # upsert por (doença, semana) atualiza sem duplicar
        return [Carga("silver.arbovirose_semanal", linhas, chaves=("doenca", "se"))]

    def agregar(self, cargas_silver, coletado_em):
        """As três doenças somadas, uma linha por semana."""
        linhas = cargas_silver[0].linhas
        por_se = {}
        for l in linhas:
            por_se.setdefault(l["se"], []).append(l)

        def soma(grupo, campo):
            return sum(x.get(campo) or 0 for x in grupo)

        gold = []
        for se, grupo in sorted(por_se.items()):
            pior = max(grupo, key=lambda x: x.get("nivel") or 0)
            nome, texto = nome_do_nivel(pior.get("nivel"))
            anterior = por_se.get(se - 100)
            inicio = grupo[0]["inicio_semana"]
            gold.append({
                "se": se,
                "ano": se // 100,
                "semana": se % 100,
                "inicio": inicio,
                "fim": inicio + timedelta(days=6),  # semana epidemiológica: domingo a sábado
                "estimados": round(soma(grupo, "casos_est")),
                # somar mínimos e máximos dá uma faixa conservadora (mais larga que a real)
                "estimados_min": round(soma(grupo, "casos_est_min")),
                "estimados_max": round(soma(grupo, "casos_est_max")),
                "notificados": round(soma(grupo, "casos")),
                "por_doenca": {x["doenca"]: round(x.get("casos_est") or 0) for x in grupo},
                "nivel": pior.get("nivel"),
                "nivel_nome": nome,
                "nivel_texto": texto,
                "nivel_doenca": pior["doenca"],
                # mesma semana do ano anterior, já consolidada, para dar contexto
                "ano_anterior": (round(sum((x.get("casos_est") or x.get("casos") or 0) for x in anterior))
                                 if anterior else None),
                "coletado_em": coletado_em,
            })
        return [Carga("gold.arbovirose_semana_cidade", gold, chaves=("se",))]
