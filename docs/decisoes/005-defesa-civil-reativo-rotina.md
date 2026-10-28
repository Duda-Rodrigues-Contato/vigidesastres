# 005 — Atendimentos da Defesa Civil: reativo x rotina

**Contexto.** Em 2024, 46% dos atendimentos são `Monitoramento`, 34% vêm
sem `Solicitacao` e 97% sem `Ocorrencia`. Somar tudo mede o trabalho da
equipe, não os eventos. Para calibrar os gatilhos de chuva interessa o que
foi acionado por um evento.

**Decisão.** Reativo = `Ocorrencia` preenchida, ou `Solicitacao` com lona,
vistoria, alagamento, deslizamento, barreira, desabamento ou dano. O resto
é rotina. A regra mora em `dominio/defesa_civil.py`. Grava-se o total, as
duas parcelas e a contagem por tipo, então dá para revisar o critério depois
sem perder o número bruto.

**Consequências.** Atendimento reativo registrado sem `Solicitacao` nem
`Ocorrencia` conta como rotina (subestima o reativo). Vistorias programadas,
se existirem, contam como reativas (superestima). Validar com a Defesa Civil.
