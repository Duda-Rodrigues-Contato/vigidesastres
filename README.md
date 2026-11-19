# Vigidesastres

Painel de vigilância de desastres e arboviroses do Recife (Django + MongoDB + PostgreSQL).

## Rodar localmente

```bash
python -m venv .venv
source .venv/Scripts/activate        # Windows (Git Bash). Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                 # preencha MONGO_URI (sem ele, mapa e dashboard ficam sem dados)
python manage.py migrate
python -m etl --listar               # fontes de dados disponíveis
python -m etl mare cemaden previsao avisos_inmet infodengue
python manage.py gerar_alertas
python manage.py runserver
```

Atalho: `bash iniciar.sh` faz tudo isso (menos criar o ambiente e o `.env`).

## Testes

```bash
python -m pytest -q
```

Os testes usam MongoDB em memória (mongomock) e SQLite: não tocam no Atlas nem no Neon.

## Mais

Decisões de arquitetura em `docs/decisoes/`.
