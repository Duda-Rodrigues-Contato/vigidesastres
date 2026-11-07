"""Cargas históricas: rodam uma vez (ou poucas), demoram horas e podem ser retomadas.

Diferente dos conectores do dia a dia (etl/fontes), gravam aos poucos e anotam
o que já foi feito em `controle_historico`: se a carga for interrompida, rodar
de novo continua do ponto onde parou.
"""
