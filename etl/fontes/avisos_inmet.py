"""Avisos meteorológicos oficiais do INMET que valem para o Recife (decisão 006).

Fonte: feed RSS público do INMET (sem cadastro). Reprodução permitida com
citação da fonte: "Avisos meteorológicos: INMET".

  bronze  bronze_avisos_inmet    o XML do feed, um documento por coleta
  silver  silver.avisos_inmet    um aviso por documento, só os do Recife

O feed mostra só os avisos recentes; a silver acumula, então com o tempo vira
o histórico de avisos oficiais para comparar com os eventos (calibração).
Horários do feed: horário de Brasília (UTC-3), gravados em UTC.
"""

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import unescape

from dominio.avisos import nivel, vale_para_recife
from etl.base import Conector
from etl.comum.http import get_bytes
from etl.destinos.base import Carga

URL = "https://apiprevmet3.inmet.gov.br/avisos/rss"
FONTE = "Avisos meteorológicos: INMET"
BRASILIA = timezone(timedelta(hours=-3))
_CELULA = re.compile(r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", re.S)


def _texto(html):
    return unescape(re.sub(r"<[^>]+>", "", html or "")).strip()


def _hora(valor):
    """'2026-10-28 00:01:00.0' (Brasília) -> datetime UTC; inválido -> None."""
    try:
        return datetime.strptime(valor[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=BRASILIA).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def ler_feed(xml):
    """Itens do RSS -> dicts com os campos da tabela da descrição."""
    avisos = []
    for item in ET.fromstring(xml).iter("item"):
        campos = {_texto(k): _texto(v) for k, v in _CELULA.findall(item.findtext("description") or "")}
        guid = item.findtext("guid") or item.findtext("link") or ""
        area = campos.get("Área", "").removeprefix("Aviso para as Áreas:")
        avisos.append({
            "id": guid.rstrip("/").rsplit("/", 1)[-1],
            "titulo": (item.findtext("title") or "").strip(),
            "status": campos.get("Status"),
            "evento": campos.get("Evento"),
            "severidade": campos.get("Severidade"),
            "inicio": _hora(campos.get("Início")),
            "fim": _hora(campos.get("Fim")),
            "descricao": campos.get("Descrição"),
            "areas": [a.strip() for a in area.split(",") if a.strip()],
            "link": campos.get("Link Gráfico") or item.findtext("link"),
        })
    return avisos


class AvisosInmet(Conector):
    nome = "avisos_inmet"
    frequencia = "diaria"
    descricao = "Avisos meteorológicos oficiais do INMET para o Recife (RSS)"

    def extrair(self):
        return get_bytes(URL).decode("utf-8")

    def documentos_bronze(self, bruto):
        return [{"xml": bruto}]

    def transformar(self, bruto, coletado_em):
        todos = ler_feed(bruto)
        if not todos:
            raise ValueError("feed de avisos do INMET veio sem itens")
        recife = [{**a, "nivel": nivel(a["severidade"]), "fonte": FONTE, "coletado_em": coletado_em}
                  for a in todos if vale_para_recife(a["areas"])]
        vigentes = [a for a in recife if a["fim"] and a["fim"] >= coletado_em]
        print(f"  [{self.nome}] {len(todos)} avisos no feed | {len(recife)} para o Recife | "
              f"{len(vigentes)} vigentes ou futuros: "
              + (", ".join(f"{a['evento']} ({a['severidade']})" for a in vigentes) or "nenhum"))
        # upsert por id: o histórico de avisos se acumula, o mesmo aviso não duplica
        return [Carga("silver.avisos_inmet", recife, chaves=("id",))]
