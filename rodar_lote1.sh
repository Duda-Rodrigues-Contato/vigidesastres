#!/bin/bash
# Lote 1: cargas (REINDESC, ERA5-Land, CEMADEN da região) e modelo de eventos.
# Roda na ordem certa e para no primeiro erro. Todas as cargas são retomáveis:
# se parar, rode de novo e ele continua de onde parou.
set -e
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate

echo "== 1/8 testes";                            python -m pytest -q
echo "== 2/8 REINDESC (dados/reindesc/*.csv)";    python -m etl.historico.reindesc
echo "== 3/8 ERA5-Land (solo e clima, ~10 min)";  python -m etl.historico.era5land
echo "== 4/8 maré calculada até 2026";            python -m etl.historico.mare --fim 2026-12-31
echo "== 5/8 CEMADEN do Recife 2025-2026 (~1 h)"; python -m etl.historico.cemaden --inicio 2025-01 --fim 2026-10
echo "== 6/8 CEMADEN dos 6 vizinhos 2016-2026 (várias horas)"
python -m etl.historico.cemaden --municipios rmr --inicio 2016-01 --fim 2026-10
python -m etl.historico.cemaden --municipios rmr --inicio 2016-01 --fim 2026-10   # repescagem das falhas
echo "== 7/8 tabela do modelo de eventos";        python -m etl.derivados.ml_eventos_dia
echo "== 8/8 modelo de eventos";                  python -m ml.eventos
echo "Lote 1 concluído. Resultado em analises/ml/saida/resultado_eventos.txt"
