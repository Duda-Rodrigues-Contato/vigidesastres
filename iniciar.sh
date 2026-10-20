#!/bin/bash
source .venv/Scripts/activate
git pull
python scripts/coletar_meteo.py
python scripts/coletar_mare.py
python manage.py runserver