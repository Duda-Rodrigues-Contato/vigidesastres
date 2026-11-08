"""Treino e avaliação do modelo de risco (etapa 5b).

    1. dados: tabela distrito x dia, sem 2014; alvo = pico acima da rotina recente (decisão 009)
    2. treino 2015-2021 | teste 2022-2024 (usado UMA vez, no fim)
    3. para árvore e XGBoost: GridSearchCV no treino (validação no tempo),
       limiar escolhido em 2021 (último ano do treino), ajuste final no treino inteiro
    4. compara no teste: limiares atuais x árvore x XGBoost
    5. salva o escolhido PELA VALIDAÇÃO (não pelo teste) em modelos/risco.joblib

Uso:
    python -m ml.treinar
"""

import sys
from pathlib import Path

from etl.destinos import obter_destino
from ml import dados, linha_base, metricas
from ml.modelo import ENTRADAS, SEM_CHUVA, ModeloRisco, matriz

SAIDA = Path(__file__).resolve().parents[1] / "analises" / "ml" / "saida"
ANO_VALIDACAO = 2021


def veredito(resultados, escolhido_nome, margem=0.02):
    """Regra fixada ANTES do experimento final: o modelo só vai para a produção se
    superar o controle sem chuva E os limiares atuais, em F1, no teste."""
    f1 = resultados[escolhido_nome]["f1"]
    controle = resultados["XGBoost SEM chuva (controle)"]["f1"]
    limiares = max(resultados["Limiares atuais (só ALTO)"]["f1"], resultados["Limiares atuais (MÉDIO+)"]["f1"])
    aprovado = f1 >= controle + margem and f1 > limiares
    return aprovado, (f"F1 {f1:.2f} | controle sem chuva {controle:.2f} | limiares atuais {limiares:.2f} -> "
                      + ("APROVADO: segue para a tela (5c)" if aprovado else
                         "NÃO APROVADO: os gatilhos atuais continuam; o modelo vira resultado do relatório"))


def executar(df, grades=None, avisar=print, salvar=True, alvo="chuva"):
    df = dados.marcar_pico(df, alvo).sort_values("data").reset_index(drop=True)
    treino, teste = dados.dividir(df)
    sub_treino, validacao = treino[treino["ano"] < ANO_VALIDACAO], treino[treino["ano"] == ANO_VALIDACAO]
    cfg = dados.ALVOS[alvo]
    avisar(f"alvo '{alvo}': algum dia entre D e D+2 com {cfg['coluna']} >= {dados.FATOR_PICO}x a rotina dos "
           f"{dados.JANELA_BASE} dias anteriores e >= rotina + {cfg['excesso']} (mínimo {cfg['minimo']})")
    avisar(f"treino {len(treino)} linhas ({int(treino['critico'].sum())} picos, {treino['critico'].mean():.1%}) | "
           f"teste {len(teste)} linhas ({int(teste['critico'].sum())} picos, {teste['critico'].mean():.1%})")

    resultados = {"Limiares atuais (só ALTO)": metricas.resumo(teste["critico"], linha_base.prever(teste, "ALTO")),
                  "Limiares atuais (MÉDIO+)": metricas.resumo(teste["critico"], linha_base.prever(teste))}
    modelos = {}
    for tipo, entradas, nome in (("arvore", ENTRADAS, "Árvore de decisão"), ("xgboost", ENTRADAS, "XGBoost"),
                                 ("xgboost", SEM_CHUVA, "XGBoost SEM chuva (controle)")):
        m = ModeloRisco(tipo, (grades or {}).get(tipo), entradas)
        ap = m.otimizar(matriz(treino, entradas), treino["critico"])
        limiar, f1_val = m.escolher_limiar(matriz(sub_treino, entradas), sub_treino["critico"],
                                           matriz(validacao, entradas), validacao["critico"])
        m.treinar(matriz(treino, entradas), treino["critico"])
        modelos[nome] = (m, f1_val)
        resultados[nome] = metricas.resumo(teste["critico"], m.prever(matriz(teste, entradas)))
        v = m.validacao
        avisar(f"{nome}: melhores {m.melhores} | precisão média na validação cruzada {ap:.3f}\n"
               f"   limiar {limiar:.3f} em {ANO_VALIDACAO}: recall {v['recall']:.0%}, precisão {v['precisao']:.0%}"
               + ("" if v["atingiu_meta"] else " (nenhum corte chegou a 80% de recall: ficou o melhor F1)"))

    avisar("\nTeste 2022-2024 (usado uma única vez):")
    for nome, r in resultados.items():
        avisar(metricas.texto(nome, r))

    ganho = resultados["XGBoost"]["f1"] - resultados["XGBoost SEM chuva (controle)"]["f1"]
    avisar(f"\nContribuição da chuva: F1 {resultados['XGBoost']['f1']:.2f} com chuva x "
           f"{resultados['XGBoost SEM chuva (controle)']['f1']:.2f} sem chuva ({ganho:+.2f})")
    candidatos = {k: v for k, v in modelos.items() if "SEM chuva" not in k}   # o controle nunca é escolhido
    escolhido_tipo = max(candidatos, key=lambda t: candidatos[t][1])          # pela VALIDAÇÃO, não pelo teste
    escolhido = candidatos[escolhido_tipo][0]
    avisar(f"Escolhido pela validação de {ANO_VALIDACAO}: {escolhido_tipo}")
    aprovado, texto_veredito = veredito(resultados, escolhido_tipo)
    avisar(f"\nVEREDITO: {texto_veredito}")
    avisar("Importância das entradas: " + ", ".join(f"{k} {v:.2f}" for k, v in list(escolhido.importancia().items())[:8]))

    teste = teste.assign(previsto=escolhido.prever(matriz(teste, escolhido.entradas)))
    avisar("\nPor distrito no teste (modelo escolhido):")
    for d, g in teste.groupby("distrito_codigo"):
        avisar(metricas.texto(f"  DS {d}", metricas.resumo(g["critico"], g["previsto"])))

    if salvar:
        caminho = escolhido.salvar(extras={"alvo": {"nome": alvo, "fator": dados.FATOR_PICO,
                                                    "janela_base": dados.JANELA_BASE,
                                                    "janela_resposta": dados.JANELA_RESPOSTA, **cfg},
                                           "teste": resultados, "aprovado": aprovado, "veredito": texto_veredito})
        avisar(f"\nModelo salvo em {caminho}")
    return resultados, escolhido


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas = []

    def avisar(s):
        print(s, flush=True)
        linhas.append(s)
    import argparse
    p = argparse.ArgumentParser(description="Treino do modelo de risco.")
    p.add_argument("--alvo", choices=list(dados.ALVOS), default="fisico",
                   help="fisico = alagamento e deslizamento (experimento final); chuva = todos os ligados à chuva")
    alvo = p.parse_args().alvo
    executar(dados.carregar(obter_destino().banco), avisar=avisar, alvo=alvo)
    (SAIDA / f"resultado_treino_{alvo}.txt").write_text("\n".join(linhas), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
