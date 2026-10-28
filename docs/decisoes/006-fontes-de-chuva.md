# 006 — Fontes de chuva: medida (CEMADEN), prevista (Open-Meteo), avisos (INMET)

**Contexto.** A chuva do painel vinha só do Open-Meteo, um modelo que enxerga
o Recife em 4 células: os 8 distritos recebiam chuva estimada, e os limiares
da literatura (derivados de pluviômetro) eram aplicados a dado de modelo.
A cliente pediu preferência por fontes oficiais (APAC, INMET, CEMADEN).

Situação das fontes oficiais (out/2026):
- CEMADEN: API da Plataforma de Entrega de Dados, cadastro gratuito, até 12
  requisições/min. 24 estações cadastradas no Recife, 17 com dados de
  chuva; os 8 distritos têm pluviômetro próprio.
  Acumulados prontos falham (erro 500); umidade do solo sem estação ativa no Recife.
- INMET: avisos meteorológicos abertos (RSS); dados horários exigem token;
  pacotes anuais históricos abertos.
- APAC: só painel, sem API.

**Decisão.** Cada fonte faz o que faz melhor:
- chuva OBSERVADA: CEMADEN, por pluviômetro, agregada por distrito
  (conector `cemaden`). O card e os alertas usam a PIOR estação do distrito
  (o pior caso do projeto é o evento não avisado); o gráfico usa a média.
  Distrito sem pluviômetro usa o mais próximo, e a tela avisa.
- chuva PREVISTA (24-48 h): Open-Meteo, rotulado como modelo.
- AVISOS oficiais: INMET (RSS), exibidos ao lado dos gatilhos do sistema.
- calibração: histórico do CEMADEN e do INMET contra a Defesa Civil.

Citação obrigatória na tela: "Dados da Rede Observacional do CEMADEN/MCTIC".

**Consequências.** Acumulados de 72 h passam a ser medida, não modelo. O
painel depende de credencial do CEMADEN no .env; se a API cair, o conector
falha e fica registrado em etl_execucoes, e a tela mostra a idade do dado.
Conta inativa por 1 ano é removida pelo CEMADEN: o ETL diário a mantém ativa.
