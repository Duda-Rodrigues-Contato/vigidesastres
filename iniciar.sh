#!/bin/bash
# ativa o ambiente virtual, seja ".venv" ou "venv", no Windows (Git Bash) ou Linux/Mac
for a in .venv/Scripts/activate .venv/bin/activate venv/Scripts/activate venv/bin/activate; do
  if [ -f "$a" ]; then source "$a"; break; fi
done
command -v python >/dev/null || { echo "Python não encontrado: crie o ambiente virtual (veja o README)"; exit 1; }
python -c "import django" 2>/dev/null || { echo "Django não instalado neste ambiente: rode pip install -r requirements.txt"; exit 1; }
git pull || echo "aviso: git pull falhou, seguindo com o código local"
# coletas do dia (o CEMADEN leva ~3 min pelo limite de requisições).
# Se uma fonte falhar, o servidor sobe mesmo assim com os dados anteriores.
python -m etl mare cemaden previsao avisos_inmet infodengue || echo "aviso: alguma coleta falhou (veja a tabela etl_execucoes)"
python manage.py migrate --noinput
python manage.py gerar_alertas || echo "aviso: não foi possível gerar os alertas de hoje"
python -m ml.demanda --prever     # previsão da semana na tela do Calendário
python manage.py runserver
