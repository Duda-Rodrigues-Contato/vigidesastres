"""Destino PostgreSQL (Neon + PostGIS): PREPARADO, AINDA NÃO ATIVADO.

Plano de ativação:
  1. criar o projeto no Neon e pôr a DATABASE_URL no .env
  2. rodar os arquivos de etl/sql/ em ordem (estrutura das tabelas)
  3. implementar os métodos abaixo com SQLAlchemy:
       - carregar com chaves  -> INSERT ... ON CONFLICT (chaves) DO UPDATE
       - carregar sem chaves  -> DELETE (com filtro) + INSERT, numa transação
       - geometrias           -> ST_GeomFromGeoJSON
  4. ETL_DESTINO=postgres no .env

O bronze continua no MongoDB mesmo depois: dado cru tem formato variado,
e documento é o formato natural para ele (mesma divisão do ETL da aula).
"""

from etl.destinos.base import Destino


class PostgresDestino(Destino):
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "O destino Postgres ainda não foi ativado. Veja o plano em etl/destinos/postgres.py"
        )

    def gravar_bronze(self, fonte, documentos, coletado_em):
        raise NotImplementedError

    def carregar(self, carga):
        raise NotImplementedError

    def registrar_execucao(self, registro):
        raise NotImplementedError
