import mongomock
import pytest
from pymongo import UpdateOne

from etl.destinos.mongo import MongoDestino


def _bulk_write_compativel(self, operacoes, **kwargs):
    """O mongomock é mais antigo que o pymongo 4.x atual e não aceita o
    lote de UpdateOne que o pymongo novo monta. Só para os testes, aplica
    as operações uma a uma. No Atlas de verdade, o bulk_write funciona."""
    for op in operacoes:
        if isinstance(op, UpdateOne):
            self.update_one(op._filter, op._doc, upsert=op._upsert)
        else:
            raise NotImplementedError(f"adaptador de teste não cobre {type(op).__name__}")


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(mongomock.collection.Collection, "bulk_write", _bulk_write_compativel)
    return mongomock.MongoClient()


@pytest.fixture
def destino(cliente):
    """Destino real, sobre um MongoDB em memória: nada vai para o Atlas."""
    return MongoDestino(cliente=cliente)
