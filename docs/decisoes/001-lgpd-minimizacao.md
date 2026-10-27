# 001 — Minimização de dados pessoais (LGPD)

**Contexto.** Os arquivos públicos do SINAN e da Defesa Civil trazem, por
pessoa: data de nascimento, endereço, CEP, raça/cor e comorbidades.
Combinados, esses campos permitem identificar alguém.

**Decisão.** Para essas fontes, o conector pede à API só os campos
necessários e grava só totais (por bairro, ano, semana). Não há bronze.
É uma exceção consciente à regra "guardar o dado bruto antes de transformar".

**Consequências.** Não dá para reprocessar com outro recorte sem baixar de
novo da fonte. Em troca, o sistema nunca guarda dado pessoal.
