"""Configuração central do ETL. Credenciais vêm do .env, nunca do código."""

import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

# Destino das camadas. Hoje tudo vai para o MongoDB; quando o Postgres
# (Neon) for ativado, silver e gold passam para lá trocando esta variável.
DESTINO = os.getenv("ETL_DESTINO", "mongo")  # "mongo" | "postgres" (futuro)

MONGO_URI = os.getenv("MONGO_URI")
MONGO_BANCO = os.getenv("MONGO_BANCO", "Recife")
DATABASE_URL = os.getenv("DATABASE_URL")  # Postgres/Neon, ainda não usado

HEADERS = {"User-Agent": "Vigidesastres/0.1 (projeto academico CESAR School)"}
TIMEOUT = 60
TENTATIVAS = 3

CKAN_RECIFE = "https://dados.recife.pe.gov.br/api/3/action"
DIR_REFERENCIA = RAIZ / "data" / "referencia"
