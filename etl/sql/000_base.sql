-- Estrutura base do Postgres (Neon). PREPARADO, AINDA NÃO APLICADO.
-- Aplicar em ordem: 000, 001, 002...  Cada arquivo pode rodar mais de uma vez.

CREATE EXTENSION IF NOT EXISTS postgis;

-- bronze continua no MongoDB; aqui ficam só as camadas limpas
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS etl;

-- uma linha por execução de conector (base da US-ID-06: alerta de falha)
CREATE TABLE IF NOT EXISTS etl.execucoes (
    id          bigserial PRIMARY KEY,
    fonte       text        NOT NULL,
    status      text        NOT NULL CHECK (status IN ('ok', 'erro')),
    inicio      timestamptz NOT NULL,
    fim         timestamptz NOT NULL,
    duracao_s   numeric,
    linhas      jsonb,
    erro        text,
    detalhe     text
);
CREATE INDEX IF NOT EXISTS execucoes_fonte_inicio ON etl.execucoes (fonte, inicio DESC);
