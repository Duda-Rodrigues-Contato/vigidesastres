# 009 — Dados do modelo de risco: alvo, dia crítico e fontes

**Contexto.** O modelo (XGBoost, com árvore de decisão e limiares atuais como
linhas de base) prevê, para cada distrito, se o dia será crítico. Isto exigiu
montar 11 anos de dados (2014-2024) e decidir o que é "crítico".

**Alvo.** Atendimentos da Defesa Civil LIGADOS À CHUVA: solicitação ou ocorrência
de lona, alagamento, inundação, deslizamento ou barreira (58% dos reativos).
Vistorias e monitoramento de imóveis ficam de fora: no DS I (centro) dominam
novembro a janeiro, todo ano, sem relação com a chuva (casarões antigos). Se a
análise `analises/ml/tipos_vs_chuva.py` mostrar que as vistorias acompanham a
chuva em algum distrito, elas podem entrar no alvo daquele distrito.

**Dia crítico.** Atendimentos ligados à chuva acima do percentil 95 DO PRÓPRIO
DISTRITO, com mínimo de 5, calculado só com os anos de treino. Um corte único
não serve: o DS VII teria 32% dos dias "críticos" e o DS VI, 0,1%. A tela mostra,
junto da probabilidade, o tamanho típico de um dia crítico em cada distrito.

**Fontes da chuva.** CEMADEN, pior pluviômetro do distrito com pelo menos 20
leituras no dia; se não houver, a estação do INMET (A301), como chuva da cidade,
coberta de 2014 a 2021. Maré: astronômica calculada (análise harmônica,
erro de 7 cm na série recente), sem ressaca.

**Tempo.** A chuva "do dia" é a do próprio dia. No uso diário vem da previsão
para amanhã; no treino, da medida. Isso equivale a uma previsão perfeita e deixa
a avaliação otimista: precisa constar no relatório.

**Limitações conhecidas.**
- A Defesa Civil registra o que ATENDEU: fins de semana e feriados têm menos
  registros (23% dos dias sem nenhum atendimento na cidade). Entram como variáveis.
- 2020-2021 (pandemia) têm muito menos atendimentos. Entra como variável.
- 1% dos atendimentos tem bairro que não casa com o IBGE (apelidos corrigidos).
- Lonas podem incluir colocação preventiva, antes da chuva.
