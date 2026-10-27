# 2. Entendimento dos dados

O levantamento completo está no doc "Levantamento de Fontes de Dados e
APIs". Resumo do que está em uso e das armadilhas encontradas:

| Fonte | Uso | Armadilha |
|---|---|---|
| Open-Meteo | chuva, temperatura, previsão | é modelo; 4 células para 8 distritos |
| Open-Meteo Marine | maré | célula a ~16 km da costa; zero no nível médio |
| InfoDengue | arboviroses por semana | municipal; semana recente subestimada (usar casos_est) |
| SINAN via portal do Recife | arboviroses por bairro, 2016–2025 | 37% descartados; datas inconsistentes; dado pessoal |
| IBGE Censo 2022 | população por bairro | conferida: soma = 1.488.920 |
| CNES | unidades de saúde | API ignora limit > 20 |
| Portal do Recife | distritos, bairros, rede de apoio, comunidades | IDs de recurso mudam; download por URL assinada |
| Defesa Civil (portal) | atendimentos 2014–2024 | 97% sem `Ocorrencia`; maioria é rotina; tem endereço |

Fechadas ao público: INMET (leitura devolve 204), APAC, CEMADEN, ESIG
(servidor não responde fora da rede da prefeitura).
