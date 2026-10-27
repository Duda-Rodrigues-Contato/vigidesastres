-- InfoDengue. PREPARADO, AINDA NÃO APLICADO.

CREATE TABLE IF NOT EXISTS silver.arbovirose_semanal (
    doenca              text        NOT NULL CHECK (doenca IN ('dengue', 'chikungunya', 'zika')),
    se                  integer     NOT NULL,   -- AAAASS
    ano                 smallint    NOT NULL,
    semana              smallint    NOT NULL CHECK (semana BETWEEN 1 AND 53),
    inicio_semana       date        NOT NULL,
    casos               integer,                -- notificados até agora
    casos_est           numeric,                -- corrigido pelo atraso de notificação
    casos_est_min       numeric,
    casos_est_max       numeric,
    nivel               smallint    CHECK (nivel BETWEEN 1 AND 4),
    rt                  numeric,
    p_rt1               numeric,
    incidencia_100k     numeric,
    receptivo           smallint,
    transmissao         smallint,
    populacao           integer,
    notificados_no_ano  integer,
    versao_modelo       text,
    coletado_em         timestamptz NOT NULL,
    PRIMARY KEY (doenca, se)
);

CREATE TABLE IF NOT EXISTS gold.arbovirose_semana_cidade (
    se              integer     PRIMARY KEY,
    ano             smallint    NOT NULL,
    semana          smallint    NOT NULL,
    inicio          date        NOT NULL,
    fim             date        NOT NULL,
    estimados       integer     NOT NULL,
    estimados_min   integer,
    estimados_max   integer,
    notificados     integer,
    por_doenca      jsonb,
    nivel           smallint,
    nivel_nome      text,
    nivel_texto     text,
    nivel_doenca    text,
    ano_anterior    integer,
    coletado_em     timestamptz NOT NULL
);
