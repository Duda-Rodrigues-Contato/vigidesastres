"""Leituras da chuva medida (CEMADEN) para as telas."""

from datetime import timedelta, timezone

from . import conexao

LEITURAS = "silver_chuva_leituras"
ESTACOES = "silver_chuva_estacoes"


def _naive_utc(dt):
    """O pymongo grava e compara datas em UTC sem fuso."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def ultima_leitura():
    """Horário (UTC, com fuso) da leitura mais recente de qualquer estação; None se não houver."""
    doc = conexao.banco()[LEITURAS].find_one({}, {"_id": 0, "datahora": 1}, sort=[("datahora", -1)])
    return doc["datahora"].replace(tzinfo=timezone.utc) if doc else None


def estacoes_ativas():
    return list(conexao.banco()[ESTACOES].find({"ativa": True}, {"_id": 0}))


def acumulado_por_estacao(horas, ate):
    """Chuva de cada estação ativa nas `horas` que terminam em `ate`, da mais chuvosa à menos.

    Usa a hora fechada da leitura (00:10 conta na hora que termina às 01:00).
    Estação sem nenhuma leitura na janela fica de fora: não é zero, é sem dado.
    """
    fim = _naive_utc(ate)
    soma = {
        g["_id"]: g["chuva_mm"]
        for g in conexao.banco()[LEITURAS].aggregate([
            {"$match": {"hora": {"$gt": fim - timedelta(hours=horas), "$lte": fim}}},
            {"$group": {"_id": "$codestacao", "chuva_mm": {"$sum": "$chuva_mm"}}},
        ])
    }
    resultado = [{**e, "chuva_mm": round(soma[e["codestacao"]], 1)}
                 for e in estacoes_ativas() if e["codestacao"] in soma]
    return sorted(resultado, key=lambda e: e["chuva_mm"], reverse=True)


def leituras_desde(inicio):
    """Leituras (estação, hora fechada, mm) a partir de `inicio`, para séries diárias."""
    return list(conexao.banco()[LEITURAS].find(
        {"hora": {"$gt": _naive_utc(inicio)}}, {"_id": 0, "codestacao": 1, "hora": 1, "chuva_mm": 1}))
