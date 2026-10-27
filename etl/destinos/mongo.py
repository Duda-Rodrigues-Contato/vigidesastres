"""Destino MongoDB: hoje recebe as três camadas."""

from pymongo import UpdateOne

from etl import config
from etl.destinos.base import Destino


def _colecao(tabela):
    """'silver.arbovirose_semanal' -> 'silver_arbovirose_semanal'."""
    return tabela.replace(".", "_")


class MongoDestino(Destino):
    def __init__(self, cliente=None):
        if cliente is None:
            import certifi
            from pymongo import MongoClient
            from pymongo.server_api import ServerApi

            if not config.MONGO_URI:
                raise RuntimeError("MONGO_URI não encontrada. Confira o .env")
            cliente = MongoClient(config.MONGO_URI, server_api=ServerApi("1"),
                                  tlsCAFile=certifi.where(), serverSelectionTimeoutMS=10000)
        self.banco = cliente[config.MONGO_BANCO]

    def gravar_bronze(self, fonte, documentos, coletado_em):
        if not documentos:
            return 0
        docs = [{"_coletado_em": coletado_em, "_fonte": fonte, **d} for d in documentos]
        self.banco[f"bronze_{fonte}"].insert_many(docs)
        return len(docs)

    def carregar(self, carga):
        colecao = self.banco[_colecao(carga.tabela)]
        if not carga.linhas:
            return 0
        if carga.chaves:
            nome_indice = "idx_" + "_".join(carga.chaves)
            colecao.create_index([(c, 1) for c in carga.chaves], unique=True, name=nome_indice)
            colecao.bulk_write([
                UpdateOne({c: l[c] for c in carga.chaves}, {"$set": l}, upsert=True)
                for l in carga.linhas
            ])
        else:
            colecao.delete_many(carga.filtro)
            colecao.insert_many([dict(l) for l in carga.linhas])
        return len(carga.linhas)

    def registrar_execucao(self, registro):
        self.banco["etl_execucoes"].insert_one(dict(registro))
