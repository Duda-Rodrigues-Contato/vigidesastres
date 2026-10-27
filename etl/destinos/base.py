"""Interface de destino: onde cada camada é gravada.

Os conectores só conhecem esta interface. Trocar o banco de uma camada é
trocar a implementação, sem mexer em conector nenhum.

Tabelas são nomeadas "camada.nome" (ex.: "silver.arbovirose_semanal"):
  - no Postgres viram schema.tabela
  - no MongoDB viram a coleção "camada_nome"
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Carga:
    """Um lote de linhas para uma tabela.

    chaves vazias  -> substitui a tabela inteira (o arquivo da fonte é a verdade)
    chaves         -> upsert: rodar de novo atualiza, não duplica
    filtro         -> com chaves vazias, substitui só as linhas que casam
    """

    tabela: str
    linhas: list
    chaves: tuple = ()
    filtro: dict = field(default_factory=dict)


class Destino(ABC):
    @abstractmethod
    def gravar_bronze(self, fonte, documentos, coletado_em):
        """Resposta da fonte como veio, mais a data da coleta."""

    @abstractmethod
    def carregar(self, carga):
        """Grava uma Carga em silver ou gold. Devolve o número de linhas."""

    @abstractmethod
    def registrar_execucao(self, registro):
        """Uma linha por execução de conector: base da US-ID-06."""
