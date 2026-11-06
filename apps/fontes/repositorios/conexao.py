"""Conexão com o MongoDB, reaproveitada entre requisições."""

import os

import certifi
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()

BANCO = os.getenv("MONGO_BANCO", "Recife")
_client = None


def get_mongo_client():
    """Uma única conexão: abrir uma por requisição estouraria o limite do Atlas."""
    global _client
    if _client is None:
        _client = MongoClient(
            os.getenv("MONGO_URI"),
            server_api=ServerApi("1"),
            tlsCAFile=certifi.where(),
            # padrão é 30 s: com o Atlas fora, a página travaria meio minuto
            serverSelectionTimeoutMS=5000,
        )
    return _client


def banco():
    return get_mongo_client()[BANCO]
