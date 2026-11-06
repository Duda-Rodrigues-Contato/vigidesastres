"""Registro das coletas do ETL (etl_execucoes), para mostrar a idade de cada fonte."""

from datetime import timezone

from . import conexao


def ultimas(fontes):
    """{fonte: {status, fim, erro}} da execução mais recente de cada fonte pedida."""
    resultado = {}
    for r in conexao.banco()["etl_execucoes"].aggregate([
        {"$match": {"fonte": {"$in": list(fontes)}}},
        {"$sort": {"inicio": -1}},
        {"$group": {"_id": "$fonte", "status": {"$first": "$status"}, "fim": {"$first": "$fim"},
                    "inicio": {"$first": "$inicio"}, "erro": {"$first": "$erro"}}},
    ]):
        quando = r.get("fim") or r.get("inicio")
        resultado[r["_id"]] = {"status": r["status"], "erro": r.get("erro"),
                               "quando": quando.replace(tzinfo=timezone.utc) if quando and quando.tzinfo is None else quando}
    return resultado
