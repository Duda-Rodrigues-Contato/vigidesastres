"""Defesa Civil do Recife - atendimentos por bairro e dia, 2014-2024.

Fonte: Portal de Dados Abertos do Recife, um CSV por ano (~80 mil linhas).

  bronze  (não há: o CSV tem endereço de quem pediu ajuda - decisão 001)
  silver  silver.defesa_civil_bairro_dia   totais por bairro e dia
  gold    gold.defesa_civil_dia_cidade     totais do Recife por dia

LGPD: a extração lê o CSV linha a linha e soma na hora. Endereco nunca é
lido para fora da linha, nem guardado. Reativo x rotina: dominio/defesa_civil.py.
"""

import re
from itertools import chain
from datetime import datetime, timezone

from dominio.defesa_civil import eh_reativo, grau_de_risco
from etl.base import Conector
from etl.comum.ckan import dataset_por_titulo
from etl.comum.http import get_bytes
from etl.comum.tabela import ler_csv
from etl.comum.texto import normalizar
from etl.destinos.base import Carga

ANOS = range(2014, 2025)
SEM_BAIRRO = "NAO INFORMADO"


def _data(valor):
    """'2024-04-03' ou '03/04/2024' -> datetime UTC à meia-noite; inválida -> None."""
    v = (valor or "").strip()[:10]
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(v, formato).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# Em 2015, 2019, 2020 e 2022 os valores de Mês..Ocorrencia estão uma coluna
# à esquerda do cabeçalho: a data cai em "Mês", a ocorrência em "Data" e a
# solicitação em "Ocorrencia". A coluna "Solicitacao" desses anos traz o
# ENDEREÇO, por isso nunca é lida nesse layout. Bairro e Grau_de_Risco batem.
LAYOUT_PADRAO = {"data": "Data", "ocorrencia": "Ocorrencia", "solicitacao": "Solicitacao"}
LAYOUT_DESLOCADO = {"data": "Mês", "ocorrencia": "Data", "solicitacao": "Ocorrencia"}
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def _layout(amostra):
    """Deslocado se 'Mês' traz data ISO na maior parte da amostra."""
    datas = sum(bool(_ISO.match((l.get("Mês") or "").strip())) for l in amostra)
    return LAYOUT_DESLOCADO if amostra and datas > len(amostra) / 2 else LAYOUT_PADRAO


def _campos(leitor):
    """Só os 5 campos usados, já no nome certo. Endereço nunca passa daqui."""
    amostra = [l for _, l in zip(range(200), leitor)]
    lay = _layout(amostra)
    for l in chain(amostra, leitor):
        yield {"Data": l.get(lay["data"]), "Ocorrencia": l.get(lay["ocorrencia"]),
               "Solicitacao": l.get(lay["solicitacao"]), "Bairro": l.get("Bairro"),
               "Grau_de_Risco": l.get("Grau_de_Risco")}


def _vazio():
    return {"total": 0, "reativos": 0, "rotina": 0, "por_tipo": {}, "por_risco": {}}


class DefesaCivil(Conector):
    nome = "defesa_civil"
    frequencia = "anual"
    descricao = "Atendimentos da Defesa Civil por bairro e dia (portal do Recife)"
    guardar_bronze = False

    def __init__(self, destino, anos=ANOS):
        super().__init__(destino)
        self.anos = list(anos)
        self.descartadas = 0  # linhas sem data válida

    def _recursos(self):
        pacote = dataset_por_titulo("Defesa Civil", "atendimentos da defesa civil")
        if not pacote:
            raise ValueError("dataset da Defesa Civil não encontrado no portal")
        por_ano = {}
        for r in pacote["resources"]:
            for ano in self.anos:
                if str(ano) in (r.get("name") or "") and (r.get("format") or "").upper() == "CSV":
                    por_ano.setdefault(ano, r["url"])
        faltando = sorted(set(self.anos) - set(por_ano))
        if faltando:
            print(f"  [{self.nome}] sem CSV para: {faltando}")
        return por_ano

    def extrair(self):
        """Já devolve o agregado {(data, bairro): contadores}. Nada individual sai daqui."""
        grupos = {}
        for ano, url in sorted(self._recursos().items()):
            for linha in _campos(ler_csv(get_bytes(url, timeout=300))):
                self._somar(grupos, linha)
        return grupos

    def _somar(self, grupos, linha):
        data = _data(linha.get("Data"))
        if data is None:
            self.descartadas += 1
            return
        bairro = normalizar(linha.get("Bairro") or "") or SEM_BAIRRO
        g = grupos.setdefault((data, bairro), _vazio())
        g["total"] += 1
        g["reativos" if eh_reativo(linha.get("Solicitacao"), linha.get("Ocorrencia")) else "rotina"] += 1
        tipo = normalizar(linha.get("Solicitacao") or "") or "SEM SOLICITACAO"
        g["por_tipo"][tipo] = g["por_tipo"].get(tipo, 0) + 1
        risco = grau_de_risco(linha.get("Grau_de_Risco"))
        if risco:
            g["por_risco"][risco] = g["por_risco"].get(risco, 0) + 1

    def transformar(self, bruto, coletado_em):
        if self.descartadas:
            print(f"  [{self.nome}] {self.descartadas} linhas sem data válida descartadas")
        linhas = [{"data": data, "ano": data.year, "bairro": bairro, **c, "coletado_em": coletado_em}
                  for (data, bairro), c in sorted(bruto.items())]
        return [Carga("silver.defesa_civil_bairro_dia", linhas, chaves=("data", "bairro"))]

    def agregar(self, cargas_silver, coletado_em):
        por_dia = {}
        for l in cargas_silver[0].linhas:
            d = por_dia.setdefault(l["data"], {"total": 0, "reativos": 0, "rotina": 0,
                                               "bairros_com_reativo": 0})
            for campo in ("total", "reativos", "rotina"):
                d[campo] += l[campo]
            d["bairros_com_reativo"] += 1 if l["reativos"] else 0
        gold = [{"data": data, "ano": data.year, **c, "coletado_em": coletado_em}
                for data, c in sorted(por_dia.items())]
        return [Carga("gold.defesa_civil_dia_cidade", gold, chaves=("data",))]
