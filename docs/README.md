# Vigidesastres — organização do projeto (CRISP-DM)

O projeto segue as seis fases do CRISP-DM. O ciclo é iterativo: cada fonte
nova volta à fase 2 antes de chegar à 6.

| Fase | O que é | Onde está |
|---|---|---|
| 1. Entendimento do negócio | o problema, quem usa, como decidem | `docs/01_negocio.md` |
| 2. Entendimento dos dados | fontes, qualidade, armadilhas | `docs/02_dados.md`, `analises/exploracao/` |
| 3. Preparação dos dados | ETL: bronze → silver → gold | `etl/` |
| 4. Modelagem | limiares e gatilhos de alerta | `dominio/` |
| 5. Avaliação | validar os gatilhos contra ocorrências reais | `analises/calibracao/` |
| 6. Implantação | painel e mapa | `vigidesastre/` |

## Camadas de dados (arquitetura medalhão)

| Camada | Banco hoje | Banco futuro | O que guarda |
|---|---|---|---|
| bronze | MongoDB | MongoDB | resposta da fonte como veio, com data da coleta |
| silver | MongoDB | PostgreSQL + PostGIS (Neon) | dado limpo e tipado |
| gold | MongoDB | PostgreSQL + PostGIS (Neon) | agregado pronto para as telas |

Nomes: tabela `silver.arbovirose_semanal` vira a coleção
`silver_arbovirose_semanal` no MongoDB e `silver.arbovirose_semanal` no
Postgres. A estrutura do Postgres já está em `etl/sql/`, não aplicada.

## Como rodar

    python -m etl --listar             fontes disponíveis
    python -m etl                      todas
    python -m etl --frequencia diaria  só as diárias
    python -m pytest                   testes

## Estado da migração

| Fonte | Padrão novo (`etl/fontes/`) | Script antigo (`scripts/`) |
|---|---|---|
| InfoDengue | ✅ piloto | `coletar_infodengue.py` (pode sair) |
| Open-Meteo, maré, CNES, distritos, áreas de risco, arboviroses por bairro, rede de apoio, comunidades | — | ainda em uso |

Decisões de projeto: `docs/decisoes/`.
