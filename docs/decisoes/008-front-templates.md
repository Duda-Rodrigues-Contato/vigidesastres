# 008 — Front-end com templates do Django, não SPA

**Contexto.** As telas (dashboard, mapa, alertas, ações, relatórios) já
existiam como templates do Django com Tailwind, Leaflet e Chart.js. Com a
reestruturação, avaliamos separar o front em React consumindo uma API.

**Decisão.** Continuar com templates do Django, organizados por app
(apps/<app>/templates/<app>/) e com componentes reaproveitáveis em
vigidesastre/templates/components/. As APIs JSON continuam existindo para o
mapa e para os formulários que gravam sem recarregar a página. Interações
mais ricas podem usar HTMX, sem etapa de build.

**Por quê.** Um front separado exigiria reescrever as telas, manter dois
projetos com deploys diferentes e autenticação por token (JWT, CORS). Os
requisitos da cliente (acesso pelo celular, mapa, formulários, relatórios)
são atendidos com layout responsivo. Com templates, o login do Django
(etapa futura) protege todas as páginas por sessão, sem código extra.

**Consequências.** O JavaScript de cada tela deve sair de dentro dos
templates para arquivos em static/ (etapa das telas). Se um dia o projeto
precisar de um aplicativo ou de outro front, as APIs JSON já são o ponto de
partida.
