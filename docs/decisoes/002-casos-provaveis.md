# 002 — Critério de casos de arboviroses

**Contexto.** Na amostra de dengue 2025, 37% das notificações eram
descartadas (CLASSI_FIN = 5). Contar todas inflaria o mapa.

**Decisão.** Casos prováveis = notificados exceto descartados, mesmo
critério dos boletins da prefeitura. Incidência por 10 mil habitantes,
com a população do Censo 2022. O ano vem do nome do arquivo, não das
datas: em 52% dos casos, SEM_PRI e DT_SIN_PRI não concordam.

**Consequências.** Bairros com pouca população dão taxas instáveis
(ex.: Bairro do Recife, 541 habitantes). Pendente: confirmar o código de
descartado no arquivo de zika.
