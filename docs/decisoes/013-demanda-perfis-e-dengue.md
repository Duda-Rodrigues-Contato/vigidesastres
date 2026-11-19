# 013 — Demanda aprovada; clima não melhora a previsão da dengue; perfis de bairro ajustados

**Contexto.** Três frentes de aprendizado de máquina além do alerta, cada uma com a regra
de aprovação fixada antes de rodar (lote 2).

**1. Previsão de demanda (aprovada).** Atendimentos reativos da Defesa Civil por distrito
e semana, com XGBoost de contagem (Poisson). Treino 2015-2021, teste 2022-2024.
- Erro médio: modelo 22,4 atendimentos x 25,1 da régua (a média daquela semana do ano no
  distrito): 11% menor (a regra pedia 10%).
- O ganho vem dos distritos grandes (DS II, IV, V, VII, VIII); nos pequenos (DS I, III,
  VI) a régua simples é igual ou melhor.
- Importância: distrito 0,40, mês 0,30, semana do ano 0,19, chuva da semana 0,04. É a
  previsão do ritmo de trabalho, útil para escalas e estoque, não para alerta.

**2. Dengue com clima (o clima não ajuda).** Casos estimados (InfoDengue) 4 semanas à
frente, com e sem temperatura, umidade e chuva (ERA5-Land). Treino 2014-2021, teste
2022-2024.
- Erro (log dos casos): 0,397 com clima x 0,399 sem: diferença nula (a regra pedia 5%).
- Os casos da semana atual dominam (importância 0,57). Junto com a etapa 4c (chuva sem
  relação além do ciclo anual): com dados semanais da cidade, o clima não melhora a
  previsão de curto prazo da dengue no Recife. Explicações prováveis: pouca variação de
  temperatura ao longo do ano, sempre favorável ao mosquito; e o peso de imunidade,
  sorotipo e ações de combate.
- Não vira aviso no painel.

**3. Perfis de risco dos bairros (K-means).** Agrupa os bairros pelo TIPO de risco:
atendimentos por tipo, eventos do REINDESC no bairro, comunidades, áreas de risco e
densidade. É um modelo sem alvo: não há aprovação, e sim coerência com o território.
- Primeira rodada: 6 grupos, silhueta 0,21, com três defeitos: o Bairro do Recife
  (cerca de 500 moradores) virou um grupo sozinho por ter taxas por 10 mil infladas; três
  grupos tinham o mesmo nome; Dois Irmãos e Guabiraba se separaram só pela baixa densidade.
- Ajustes: taxas cortadas no percentil 95; nenhum grupo com menos de 3 bairros (o bairro
  isolado vai para o grupo mais parecido); nomes pelas duas características mais fortes,
  com a categoria na frente (encosta, planície, imóveis, comunidades, áreas de risco).
- Resultado atual em `analises/ml/saida/resultado_perfis.txt` e na camada "Perfis de
  risco" do mapa. Validar com a equipe da Vigidesastres se os grupos fazem sentido.
