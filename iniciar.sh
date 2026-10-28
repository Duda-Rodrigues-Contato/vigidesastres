#!/bin/bash
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
git pull
python scripts/coletar_meteo.py
python -m etl mare infodengue
python manage.py runserver
