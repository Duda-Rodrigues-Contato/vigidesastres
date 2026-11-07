"""Modelo de risco do Vigidesastres (etapa 5): dados, linha de base, árvore e XGBoost.

Mesma organização da atividade de AVD: preparar -> dividir -> otimizar -> treinar -> avaliar -> salvar.
A divisão é POR TEMPO (treino 2015-2021, teste 2022-2024) e o "dia crítico" é
definido só com os anos de treino (decisão 009).
"""
