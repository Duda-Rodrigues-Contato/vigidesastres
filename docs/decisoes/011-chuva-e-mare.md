# 011 — Chuva x maré: sem efeito na escala diária; sinal provável, não confirmado, na hora da chuva

**Contexto.** A hipótese da equipe: alagamentos na planície do Recife pioram quando a
chuva forte coincide com a maré alta, que represa os canais. Os gatilhos atuais
(`dominio/limiares.py`) já têm uma regra de chuva com maré alta, nunca validada.

**Dados.**
- Maré astronômica calculada (análise harmônica, 2014-2026, diária e horária).
- Nível total do mar e ressaca do GTSM (Copernicus, Deltares, forçado com ERA5),
  2014-2024, no ponto em frente ao Porto do Recife (lat -8,071; lon -34,878).
- Chuva do CEMADEN por distrito, com a hora do pico de chuva de cada dia.
- Alvo: alagamento registrado pela Defesa Civil no distrito, no dia ou no seguinte,
  só nos distritos de planície (DS I, IV, V e VI).
- Pedido de dados do marégrafo do Porto do Recife feito ao BNDO (Marinha).

**Achados.**
1. A maré calculada concorda com o nível total do GTSM (correlação de 0,88 em 4.018
   dias): fica validada por uma fonte independente e pode cobrir 2025-2026.
2. A ressaca no Recife é pequena e estável: máxima anual de 0,13 a 0,17 m em 11 anos
   (mediana diária 0,08 m), contra até 2,7 m de amplitude da maré. Ela é igual em dias
   com e sem alagamento (0,077 x 0,079 m) e não acompanha a chuva (correlação -0,05).
3. Mapas de calor (chuva x maré calculada e chuva x nível total): a chance de
   alagamento cresce com a chuva (0,7% em dias secos; 12 a 32% acima de 55 mm), mas
   não segue o nível do mar.
4. Experimentos com e sem maré (XGBoost, treino 2015-2020, limiar em 2021, teste
   2022-2024; regra fixada antes: efeito se a precisão média subir pelo menos 0,02):

| Experimento | Precisão média com x sem maré | Margem de erro (95%, bootstrap por dia) | Maré ajudou em |
|---|---|---|---|
| A. Escala diária (nível máximo e ressaca) | 0,058 x 0,069 (-0,011) | -0,038 a +0,005 | 8% das repetições |
| B. Maré na hora do pico de chuva | 0,125 x 0,106 (+0,019) | -0,008 a +0,058 | 92% das repetições |

No B, o F1 foi de 0,11 para 0,21. A primeira versão do B, com a chuva horária do INMET
(2015-2021), teve só 8 dias com alagamento no teste e foi inconclusiva.

**Decisão.**
- Na escala diária, a maré NÃO tem efeito detectável: a margem de erro fica quase toda
  abaixo de zero.
- Na coincidência horária entre o pico de chuva e a preamar, há um SINAL PROVÁVEL mas NÃO
  CONFIRMADO: a maré melhorou o modelo em 92% das repetições, mas a margem de erro ainda
  cruza o zero e a diferença (+0,019) ficou abaixo do limite fixado (+0,02).
- O gatilho de chuva com maré alta continua em `dominio/limiares.py`, marcado como "sinal
  fraco, não confirmado". A informação que importa para a equipe é a coincidência hora a
  hora entre chuva forte e preamar (gráfico das próximas 48 h), não a maré máxima do dia.

**Consequências.**
- No modelo de eventos (REINDESC), entram a maré na hora do pico de chuva e a chuva do
  pico; a ressaca e o nível máximo diário saem.
- Para confirmar ou descartar o sinal: mais anos de alagamentos (2025 em diante), o
  nível do mar medido pelo BNDO e eventos com horário (REINDESC).
- Limitação: a Defesa Civil não registra a hora do alagamento; o efeito da maré pode ser
  local (perto dos canais e do estuário) e se diluir na escala do distrito.
