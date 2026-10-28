#!/bin/bash
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
git pull
# coletas do dia (o CEMADEN leva ~3 min pelo limite de requisições)
python -m etl mare cemaden previsao avisos_inmet infodengue
python manage.py runserver
