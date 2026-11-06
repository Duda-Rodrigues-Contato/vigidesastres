# 007 — Dois bancos: PostgreSQL para o sistema, MongoDB para as fontes

**Contexto.** Até aqui tudo ficava no MongoDB. O sistema passa a ter dados
próprios, criados pelos usuários: alertas, ações de resposta e, depois,
usuários e registros de emergência. Esses dados precisam de relacionamentos
(ação pertence a um alerta), transações e histórico de alterações.

**Decisão.** PostgreSQL (Neon) é o banco do Django: usuários, alertas, ações,
com models e migrations. O MongoDB continua com os dados das fontes (bronze,
silver, gold), escritos só pelo ETL e lidos pelo Django via apps/fontes.
A conexão vem de DATABASE_URL no .env; sem ela (testes, CI), usa SQLite.

**Consequências.** Dois bancos para configurar no .env. A separação deixa
claro quem escreve onde: o ETL nunca toca no Postgres, e as telas nunca
escrevem nos dados das fontes. A decisão 004 (Postgres preparado para o ETL)
continua valendo como alternativa futura para as fontes.
