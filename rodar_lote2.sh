#!/bin/bash
# Lote 2: demanda (contagem), perfis de bairro (K-means) e dengue com clima.
set -e
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
echo "== 1/4 testes";                      python -m pytest -q
echo "== 2/4 perfis de risco dos bairros"; python -m ml.perfis
echo "== 3/4 previsão de demanda";         python -m ml.demanda
echo "== 4/4 dengue com clima";            python -m ml.dengue_clima
echo "Lote 2 concluído. Resultados em analises/ml/saida/ e a camada 'Perfis de risco' no mapa."
