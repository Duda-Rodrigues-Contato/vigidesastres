from etl import config


def obter_destino():
    """O destino configurado no .env (ETL_DESTINO)."""
    if config.DESTINO == "mongo":
        from etl.destinos.mongo import MongoDestino
        return MongoDestino()
    if config.DESTINO == "postgres":
        from etl.destinos.postgres import PostgresDestino
        return PostgresDestino()
    raise ValueError(f"ETL_DESTINO desconhecido: {config.DESTINO}")
