"""Classe base dos conectores (CRISP-DM, fase 3: preparação dos dados).

Cada fonte implementa só o que é dela:
    extrair()                 -> bruto, como veio da fonte
    transformar(bruto, quando)-> lista de Carga para a SILVER
    agregar(silver, quando)   -> lista de Carga para a GOLD (opcional)

O resto é igual para todos e mora aqui: carimbo de coleta, bronze,
cronômetro, registro da execução e tratamento de falha.
"""

import time
import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timezone


class Conector(ABC):
    nome = "base"
    frequencia = "diaria"  # diaria | semanal | anual
    descricao = ""

    # LGPD: fontes com dado pessoal (SINAN, Defesa Civil) põem False e
    # não guardam bronze - o conector já extrai só o agregado.
    guardar_bronze = True

    def __init__(self, destino):
        self.destino = destino

    @abstractmethod
    def extrair(self):
        ...

    def documentos_bronze(self, bruto):
        """Como o bruto vira documentos de bronze. Padrão: uma lista de dicts."""
        return bruto if isinstance(bruto, list) else [bruto]

    @abstractmethod
    def transformar(self, bruto, coletado_em):
        ...

    def agregar(self, cargas_silver, coletado_em):
        return []

    def executar(self):
        """Roda as etapas e registra o resultado. Nunca deixa a exceção
        escapar: o orquestrador segue para a próxima fonte."""
        coletado_em = datetime.now(timezone.utc)
        inicio = time.monotonic()
        registro = {"fonte": self.nome, "inicio": coletado_em, "status": "ok",
                    "linhas": {}, "erro": None}
        try:
            bruto = self.extrair()
            if self.guardar_bronze:
                registro["linhas"]["bronze"] = self.destino.gravar_bronze(
                    self.nome, self.documentos_bronze(bruto), coletado_em)

            silver = self.transformar(bruto, coletado_em)
            gold = self.agregar(silver, coletado_em)
            for carga in silver + gold:
                registro["linhas"][carga.tabela] = self.destino.carregar(carga)
        except Exception as erro:  # noqa: BLE001 - registrar qualquer falha é o objetivo
            registro["status"] = "erro"
            registro["erro"] = f"{type(erro).__name__}: {erro}"
            registro["detalhe"] = traceback.format_exc(limit=5)

        registro["duracao_s"] = round(time.monotonic() - inicio, 1)
        registro["fim"] = datetime.now(timezone.utc)
        try:
            self.destino.registrar_execucao(registro)
        except Exception as erro:  # noqa: BLE001
            print(f"  [{self.nome}] não foi possível registrar a execução: {erro}")

        situacao = "OK" if registro["status"] == "ok" else f"ERRO - {registro['erro']}"
        print(f"[{self.nome}] {situacao} em {registro['duracao_s']}s | {registro['linhas']}")
        return registro
