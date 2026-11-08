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

**Ajustes depois da carga completa.**
- 2014 fica fora do treino e do teste: o arquivo da Defesa Civil daquele ano tem
  só 449 atendimentos ligados à chuva, contra 9 a 16 mil nos outros anos. Treino:
  2015-2021; teste: 2022-2024.
- Vistorias ficam fora do alvo em todos os distritos: a correlação delas com a
  chuva de 3 dias (0,03 a 0,20) é sempre menor que a das lonas (0,30 a 0,34), e no
  DS I é praticamente zero (`analises/ml/tipos_vs_chuva.py`).
- A tabela separa alagamento e deslizamento (`atendimentos_alagamento`,
  `atendimentos_deslizamento`): a maré só deveria pesar no alagamento, nos
  distritos de planície (DS I, IV, V, VI).

**Revisão do alvo depois do primeiro treino.** Com o alvo "acima do p95 do
distrito", o XGBoost aprendeu o calendário da Defesa Civil (mês, fim de semana,
dia da semana e pandemia somavam metade da importância) e perdeu para os limiares
atuais (F1 0,12 contra 0,20). Os "dias críticos" eram, em boa parte, dias de muito
trabalho programado (campanha de lonas na estação chuvosa), e os registros caem
ano a ano (1,7% de dias críticos no teste contra 4% no treino). Novo alvo: PICO —
algum dia entre D e D+2 com atendimentos ligados à chuva de pelo menos 3 vezes a
média diária dos 28 dias anteriores, com mínimo de 5. A janela de 3 dias absorve
o atraso de resposta e o fim de semana. Limitação: o início de uma campanha de
lonas pode aparecer como pico nos primeiros dias, até a rotina subir. Saem das entradas dia da semana, fim de
semana, feriado e pandemia: num alerta, prever "segunda-feira" não ajuda.

