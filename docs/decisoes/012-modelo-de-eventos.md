# 012 — Modelo de eventos (REINDESC): a chuva prevê eventos; o modelo não foi aprovado; os gatilhos avisam 47% no Recife

**Contexto.** O modelo de risco com a Defesa Civil falhou porque o alvo misturava evento e
rotina (decisão 010). O REINDESC (CEMADEN) registra EVENTOS com data: 825 ocorrências de
2016 a 2026 no Recife e em 6 municípios vizinhos (374 município-dias), 75% deslizamentos.

**Método.** Unidade x dia (8 distritos do Recife + 6 municípios), 2016-2026. Entradas:
chuva do pior pluviômetro (dia, véspera, 3 e 7 dias, 72 h antes, intensidade, chuva com
memória), maré na hora do pico de chuva (decisão 011), umidade do solo do ERA5-Land na
véspera, mês e unidade. Ajuste 2016-2022, limiar em 2023, teste 2024-2026 (anos nunca
usados). Regressão logística e XGBoost; controle sem chuva e sem solo; régua: gatilhos
atuais. Avaliação da probabilidade (precisão média, Brier, calibração), margem de erro
por bootstrap de dias e estabilidade ano a ano. Regra fixada antes, no Recife: precisão
média >= controle + 0,02 com limite inferior da margem > 0, E F1 > melhor gatilho.

**Resultados (teste 2024-2026).**
| | Recife (36 eventos) | Região (145 eventos) |
|---|---|---|
| Precisão média com chuva e solo (XGBoost) | 0,113 | 0,347 |
| Precisão média do controle | 0,015 | 0,055 |
| F1 do modelo escolhido (XGBoost) | 0,08 | 0,20 |
| F1 dos gatilhos (só ALTO) | 0,09 (recall 47%) | 0,20 (recall 76%) |
| F1 da regressão logística (não escolhida) | 0,14 | 0,30 |

Margem de erro da diferença para o controle, no Recife: +0,014 a +0,226 (99% dos sorteios).
Estabilidade: com chuva e solo venceu o controle em todos os anos de 2020 a 2026.
Calibração: na faixa de maior risco, previsto 4,6% e observado 4,5%.
Importância: chuva de 3 dias 0,50; umidade do solo ~0,03 (célula de 9 km, grosseira).

**Decisão.** NÃO APROVADO: passou no critério 1 (a chuva prevê eventos, com margem de erro
positiva) e falhou no 2 por 0,01 de F1. O limiar, escolhido em 2023 (39 eventos), saiu em
0,002 e gerou alertas demais. A regressão logística teria superado os gatilhos, mas não foi
a escolhida pela validação; isso fica como observação, não como resultado. Os gatilhos
atuais continuam no sistema.

**Consequências.**
- Primeira avaliação dos gatilhos contra eventos reais: avisariam 47% dos dias com evento
  no Recife e 76% na região, com cerca de 10 alertas por evento.
- O teste 2024-2026 está gasto. Próxima versão: limiar escolhido com vários anos de
  validação; avaliação em 2027.
- Nenhum evento de grande porte no período de teste: essa pergunta segue em aberto.
