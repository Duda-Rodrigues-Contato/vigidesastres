"""Apoio ao painel de demonstração do ML (app_ml.py): leitura do banco e dos arquivos salvos.

Fica separado do app para os testes trocarem estas funções por dados de mentira."""

from datetime import date, datetime, timedelta

import joblib
import numpy as np
import pandas as pd

from etl.destinos import obter_destino
from etl.destinos.base import Carga
from ml import demanda


def _banco():
    return obter_destino().banco


def ler_diario(desde=None, ate=None):
    filtro = {"ano": {"$gte": 2015, "$lte": 2024}}
    if desde or ate:
        filtro = {"data": {"$gte": desde or datetime(2015, 1, 1), "$lt": ate or datetime(2100, 1, 1)}}
    return demanda._ler_diario(_banco(), filtro)


def ler_avaliacao():
    return joblib.load(demanda.AVALIACAO) if demanda.AVALIACAO.exists() else None


def ler_pacote():
    arquivo = demanda.PASTA_MODELOS / "demanda.joblib"
    return joblib.load(arquivo) if arquivo.exists() else None


def ler_tabela(nome):
    return pd.DataFrame(list(_banco()[nome].find({}, {"_id": 0})))


def gravar_simulacao(docs):
    obter_destino().carregar(Carga("gold.demanda_simulacoes", docs, chaves=("distrito_codigo", "inicio_semana")))


def simular(dia, pacote):
    """Previsão dos 8 distritos para a semana de `dia`, com o real quando a semana já passou."""
    inicio = demanda.inicio_da_semana(dia)
    desde = datetime.combine(inicio - timedelta(days=60), datetime.min.time())
    ate = datetime.combine(inicio + timedelta(days=7), datetime.min.time())
    diario = ler_diario(desde, ate)
    dados_ate = pd.to_datetime(diario["data"]).max() if len(diario) else None
    docs = demanda.prever(diario, pacote, hoje=dia, dados_ate=min(dados_ate, pd.Timestamp(inicio))
                          if dados_ate is not None else None)
    real = demanda.semanal(diario).set_index(["distrito_codigo", "inicio"])["atendimentos"] if len(diario) else {}
    for d in docs:
        valor = real.get((d["distrito_codigo"], pd.Timestamp(d["inicio_semana"])), np.nan) if len(real) else np.nan
        d["real"] = None if pd.isna(valor) else float(valor)
        d["origem"] = "simulador"
    return docs


# Análises que não passaram na regra fixada antes de rodar (decisões 010 a 013).
FALHAS = [
    {"titulo": "Dia crítico por distrito", "decisao": "010",
     "pergunta": "Prever se amanhã será um dia com alagamento ou deslizamento em cada distrito.",
     "modelo": "XGBoost classificador, divisão por tempo, TimeSeriesSplit + GridSearch, scale_pos_weight, "
               "limiar escolhido para recall de 80% na validação.",
     "regra": "Superar os gatilhos de chuva que a Defesa Civil já usa (F1).",
     "numeros": [("F1 do modelo", "0,17"), ("F1 dos gatilhos de chuva", "0,33")],
     "por_que": "Os eventos físicos são raros e o registro de atendimento não mede o evento em si (depende de "
                "alguém ligar). A chuva acumulada em 7 dias, a entrada mais forte, já está nos gatilhos simples: "
                "o modelo não acrescenta informação além da regra.",
     "aprendizado": "O alvo mudou três vezes (p95, pico 3× a rotina, eventos físicos), sempre registrado. "
                    "Testar contra a regra atual, e não contra 'chutar sempre não', evitou um 95% de acurácia enganoso."},
    {"titulo": "Chuva × maré", "decisao": "011",
     "pergunta": "A maré alta junto com a chuva aumenta o risco de alagamento no Recife?",
     "modelo": "O mesmo modelo com e sem maré; diferença de precisão média com intervalo de confiança "
               "por bootstrap de dias.",
     "regra": "Intervalo de confiança da melhora inteiro acima de zero.",
     "numeros": [("Maré do dia: melhora", "IC −0,038 a +0,005"), ("Maré na hora do pico: melhora", "+0,019 (IC −0,008 a +0,058)"),
                 ("Bootstrap a favor", "92%")],
     "por_que": "Não há marégrafo nem medição de nível de rio pública no Recife: a maré é calculada (análise "
                "harmônica, validada com o GTSM do Copernicus, correlação 0,88). Chuvas fortes que coincidem com "
                "maré alta são poucas, então o intervalo ainda cruza o zero.",
     "aprendizado": "Resultado: sinal provável, não confirmado. A maré da hora do pico importa mais que a do dia. "
                    "Pedido de dados ao BNDO (Marinha) e análise por bairros sensíveis como próximos passos."},
    {"titulo": "Eventos na região metropolitana (REINDESC)", "decisao": "012",
     "pergunta": "Prever dias com desastre registrado no REINDESC nos 14 municípios da RMR.",
     "modelo": "XGBoost com ERA5-Land e CEMADEN, contra um controle sem chuva e contra os gatilhos.",
     "regra": "Superar os gatilhos de chuva no F1.",
     "numeros": [("Precisão média: modelo × controle", "0,113 × 0,015"), ("F1: modelo × gatilhos", "0,08 × 0,09"),
                 ("Gatilhos atuais avisam", "47% no Recife, 76% na região")],
     "por_que": "São só 825 ocorrências em 10 anos: com tão poucos positivos, nenhum limiar dá um alarme sim/não "
                "confiável. Mas o modelo ORDENA bem os dias por risco (venceu o controle em todos os anos de 2020 a 2026).",
     "aprendizado": "Não serve como alarme, serve como índice de risco de 0 a 1. E mostrou um achado prático: os "
                    "gatilhos atuais deixam passar metade dos eventos do Recife."},
    {"titulo": "Dengue com clima", "decisao": "013",
     "pergunta": "Temperatura, umidade e chuva ajudam a prever os casos de dengue 4 semanas à frente?",
     "modelo": "XGBoost com e sem as variáveis de clima (InfoDengue + Open-Meteo).",
     "regra": "Pelo menos 5% menos erro com clima.",
     "numeros": [("Erro com clima", "0,397"), ("Erro sem clima", "0,399")],
     "por_que": "Os casos das semanas anteriores (importância 0,57 + 0,15) já carregam o efeito do clima e da "
                "sazonalidade. O clima não traz informação nova para 4 semanas à frente.",
     "aprendizado": "Coerente com a análise chuva→dengue da etapa 4, que também não achou efeito além da sazonalidade."},
    {"titulo": "Perfis de bairro (agrupamento)", "decisao": "013",
     "pergunta": "Os 92 bairros formam grupos de risco distintos?",
     "modelo": "K-means com taxas por 10 mil habitantes (cortadas no p95), escolha de k pela silhueta, "
               "mínimo de 3 bairros por grupo.",
     "regra": "Grupos interpretáveis e silhueta que indique estrutura.",
     "numeros": [("Silhueta", "0,24"), ("Grupos", "encosta 24 · comunidades/alagamento 32 · baixo risco 36")],
     "por_que": "Pela escala de Kaufman & Rousseeuw, até 0,25 não há estrutura substancial: o risco varia de forma "
                "contínua entre os bairros, sem fronteiras claras. Alguns 'Altos' caíram em baixo risco, "
                "provavelmente por como o nome do bairro aparece nos registros.",
     "aprendizado": "Usado só como descrição no mapa, para validar com a Mariana (Vigidesastres), não como classificação."},
]
