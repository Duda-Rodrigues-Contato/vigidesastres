# 004 — PostgreSQL preparado, não ativado

**Contexto.** O projeto vai precisar de banco relacional (consultas
espaciais, cruzamentos, exportação para planilha). O ETL da disciplina de
Análise e Visualização de Dados usa NeonDB para a camada silver.

**Decisão.** Silver e gold vão para PostgreSQL + PostGIS no Neon, mas não
agora. Os conectores gravam por uma interface (`etl/destinos/base.py`); a
implementação Postgres está desenhada e desligada. As views leem por
`vigidesastre/src/repositorios/`. A estrutura das tabelas está em
`etl/sql/`, versionada.

Sem GeoDjango: exigiria a biblioteca GDAL, de instalação difícil no
Windows. Consultas espaciais ficam no SQL (`ST_AsGeoJSON`).

**Consequências.** Ativar o Postgres = aplicar `etl/sql/`, implementar
`PostgresDestino` e trocar `ETL_DESTINO`. Nenhum conector muda.
