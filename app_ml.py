"""Painel de demonstração do Machine Learning do Vigidesastres (no formato da Aula 12 de AVD).

Separado do site em Django: é para apresentar o modelo, não para a equipe da Vigidesastres.

Antes de abrir:
    python -m ml.demanda                         avaliação (gera analises/ml/saida/demanda_avaliacao.joblib)
    python -m ml.demanda --salvar --ate-ano 2023 modelo para o simulador (não viu 2024)
Abrir:
    streamlit run app_ml.py
"""

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from dominio.distritos import nome_distrito
from ml import demanda, painel

st.set_page_config(page_title="ML · Vigidesastres", layout="wide")
st.title("Vigidesastres · Machine Learning")
st.caption("Previsão da demanda semanal de atendimentos da Defesa Civil por distrito sanitário do Recife")


@st.cache_data(ttl=600)
def carregar_semanal():
    return demanda.semanal(painel.ler_diario())


@st.cache_data(ttl=600)
def carregar_avaliacao():
    return painel.ler_avaliacao()


@st.cache_resource
def carregar_pacote():
    return painel.ler_pacote()


aba_dados, aba_modelo, aba_simulador, aba_gold, aba_falhas = st.tabs(
    ["Os dados", "O modelo", "Simulador", "Previsões salvas", "O que não passou"])

# ---------------------------------------------------------------- Os dados
with aba_dados:
    s = carregar_semanal()
    s["distrito"] = s["distrito_codigo"].map(nome_distrito)
    recife = s.groupby("inicio", as_index=False)["atendimentos"].sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Distrito-semanas", f"{len(s):,}".replace(",", "."))
    c2.metric("Atendimentos por semana (Recife)", f"{recife['atendimentos'].mean():.0f}")
    c3.metric("Período", f"{s['inicio'].min():%Y} a {s['inicio'].max():%Y}")
    st.caption("Fonte: atendimentos reativos da Defesa Civil (dados abertos do Recife) e chuva do CEMADEN/INMET, "
               "na tabela gold.ml_distrito_dia.")

    st.plotly_chart(px.line(recife, x="inicio", y="atendimentos", title="Atendimentos por semana no Recife",
                            labels={"inicio": "semana", "atendimentos": "atendimentos"}))
    c1, c2 = st.columns(2)
    por_mes = s.groupby("mes", as_index=False)["atendimentos"].mean()
    c1.plotly_chart(px.bar(por_mes, x="mes", y="atendimentos", title="Média por distrito e semana, por mês",
                           labels={"mes": "mês", "atendimentos": "atendimentos/semana"}))
    c2.plotly_chart(px.box(s.sort_values("distrito_codigo"), x="distrito", y="atendimentos",
                           title="Atendimentos por semana em cada distrito"))
    st.plotly_chart(px.scatter(s, x="chuva_semana_anterior_mm", y="atendimentos", color="distrito", opacity=0.4,
                               title="Chuva da semana anterior × atendimentos da semana",
                               labels={"chuva_semana_anterior_mm": "chuva da semana anterior (mm)"}))
    st.caption("A chuva sozinha explica pouco: semanas com a mesma chuva têm demandas muito diferentes. "
               "O que mais pesa é o patamar de cada distrito e a época do ano.")

# ---------------------------------------------------------------- O modelo
with aba_modelo:
    av = carregar_avaliacao()
    if av is None:
        st.warning("Avaliação ainda não salva. Rode `python -m ml.demanda`.")
    else:
        tabela = pd.DataFrame(av["tabela"]).set_index("versao")
        esc, regua = tabela.loc[av["escolhida"]], tabela.loc["régua (o normal)"]
        ingenuo = tabela.loc["ingênuo (igual à semana passada)"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Erro (WAPE) no teste", f"{esc['wape']:.0%}")
        c2.metric("R² no teste", f"{esc['r2']:.2f}")
        c3.metric("Menos erro que a régua", f"{1 - esc['mae'] / regua['mae']:.0%}")
        c4.metric("Menos erro que 'semana passada'", f"{1 - esc['mae'] / ingenuo['mae']:.0%}")
        (st.success if av["aprovado"] else st.error)(
            f"Versão escolhida: **{av['escolhida']}** · {'APROVADO' if av['aprovado'] else 'NÃO APROVADO'} "
            f"(regra fixada antes de rodar: errar pelo menos {av['ganho_minimo']:.0%} menos que a régua no teste 2022-2024)")

        st.subheader("Versões testadas")
        mostrar = tabela.rename(columns={"validacao": "erro na validação (treino)", "mae": "MAE (teste)",
                                         "wape": "WAPE (teste)", "r2": "R² (teste)"})
        st.dataframe(mostrar.style.format({"erro na validação (treino)": "{:.1f}", "MAE (teste)": "{:.1f}",
                                           "WAPE (teste)": "{:.0%}", "R² (teste)": "{:.2f}"}, na_rep="—"))
        st.info("**Como ler.** A versão 0 usava a chuva da própria semana, que ninguém sabe na segunda-feira: era "
                "vazamento de dados. Corrigida (versão 1), o ganho caiu de 11% para 6%. A demanda das semanas "
                "anteriores (versão 2) trouxe o maior salto. A escolha entre 1 e 4 é feita pelo erro na validação "
                "do treino, nunca pelo teste.")

        teste = av["teste"].copy()
        teste["distrito"] = teste["distrito_codigo"].map(nome_distrito)
        escolhido = st.selectbox("Distrito", [nome_distrito(c) for c in sorted(teste["distrito_codigo"].unique())])
        g = teste[teste["distrito"] == escolhido].melt(id_vars="inicio", value_vars=["atendimentos", "previsto", "normal"],
                                                       var_name="série", value_name="valor")
        st.plotly_chart(px.line(g, x="inicio", y="valor", color="série",
                                title=f"{escolhido}: real × previsto × normal no teste (2022-2024)",
                                labels={"inicio": "semana", "valor": "atendimentos"}))

        c1, c2 = st.columns(2)
        erros = teste.assign(modelo=(teste["previsto"] - teste["atendimentos"]).abs(),
                             régua=(teste["normal"] - teste["atendimentos"]).abs())
        erros = erros.groupby("distrito", as_index=False)[["modelo", "régua"]].mean().melt(
            id_vars="distrito", var_name="quem", value_name="erro")
        c1.plotly_chart(px.bar(erros, x="distrito", y="erro", color="quem", barmode="group",
                               title="Erro médio por semana, por distrito", labels={"erro": "atendimentos"}))
        imp = pd.Series(next(iter(av["importancia"].values()))).nlargest(8).sort_values()
        c2.plotly_chart(px.bar(imp, orientation="h", title="Entradas mais importantes",
                               labels={"value": "importância", "index": ""}))

# ---------------------------------------------------------------- Simulador
with aba_simulador:
    pacote = carregar_pacote()
    if pacote is None:
        st.warning("Modelo ainda não salvo. Rode `python -m ml.demanda --salvar --ate-ano 2023`.")
    else:
        st.caption(f"Modelo treinado com dados até a semana de {pacote['ultima_semana']}. "
                   "Para uma demonstração honesta, escolha semanas depois disso.")
        with st.form("semana"):
            c1, c2 = st.columns(2)
            dia = c1.date_input("Um dia da semana a prever", value=date(2024, 5, 20))
            distrito = c2.selectbox("Distrito em destaque", list(range(1, 9)), format_func=nome_distrito, index=6)
            gravar = st.checkbox("Gravar a previsão na camada gold")
            enviar = st.form_submit_button("Prever")
        if enviar:
            if pd.Timestamp(demanda.inicio_da_semana(dia)) <= pd.Timestamp(pacote["ultima_semana"]):
                st.warning("O modelo já viu essa semana no treino: o acerto aqui não vale como teste.")
            docs = painel.simular(dia, pacote)
            d = next(x for x in docs if x["distrito_codigo"] == distrito)
            c1, c2, c3 = st.columns(3)
            c1.metric(f"Previsto · {d['distrito']}", f"{d['previsto']:.0f}",
                      None if d["variacao"] is None else f"{d['variacao']:+.0%} do normal", delta_color="off")
            c2.metric("Normal da época", "—" if d["normal"] is None else f"{d['normal']:.0f}")
            c3.metric("Real", "semana ainda não aconteceu" if d["real"] is None else f"{d['real']:.0f}")
            if not d["completa"]:
                st.info(f"Sem os atendimentos da semana anterior (dados até {d['dados_ate']}): usada a versão "
                        "reduzida, só calendário e chuva.")
            todos = pd.DataFrame(docs).melt(id_vars="distrito", value_vars=["previsto", "normal", "real"],
                                             var_name="série", value_name="atendimentos")
            st.plotly_chart(px.bar(todos, x="distrito", y="atendimentos", color="série", barmode="group",
                                   title=f"Semana de {docs[0]['inicio_semana']}: todos os distritos"))
            if gravar:
                painel.gravar_simulacao(docs)
                st.info("Previsão gravada em gold.demanda_simulacoes.")

# ---------------------------------------------------------------- Previsões salvas
with aba_gold:
    for titulo, tabela in (("Previsão da semana (a que aparece no Calendário do site)", "gold_demanda_previsao"),
                           ("Previsões gravadas pelo simulador", "gold_demanda_simulacoes")):
        st.subheader(titulo)
        try:
            gold = painel.ler_tabela(tabela)
        except Exception:
            gold = pd.DataFrame()
        if gold.empty:
            st.info("Nada gravado ainda. Use o simulador ou rode `python -m ml.demanda --prever`.")
            continue
        colunas = [c for c in ["inicio_semana", "distrito", "previsto", "normal", "real", "versao", "gerado_em"]
                   if c in gold]
        st.metric("Linhas", len(gold))
        st.dataframe(gold[colunas].sort_values(colunas[:2]), key=f"tabela_{tabela}")
        if "real" in gold and gold["real"].notna().any():
            com_real = gold.dropna(subset=["real"])
            st.plotly_chart(px.scatter(com_real, x="real", y="previsto", color="distrito",
                                       title="Previsto × real (quanto mais perto da diagonal, melhor)"),
                            key=f"dispersao_{tabela}")

# ---------------------------------------------------------------- O que não passou
with aba_falhas:
    st.write("Cada análise teve uma **regra de aprovação fixada antes de rodar** e uma comparação com uma "
             "alternativa simples. Estas não passaram; o resultado negativo também é registrado "
             "(`docs/decisoes/`).")
    for f in painel.FALHAS:
        with st.container(border=True):
            st.subheader(f"{f['titulo']} · decisão {f['decisao']}")
            st.write(f"**Pergunta:** {f['pergunta']}")
            st.write(f"**Modelo:** {f['modelo']}")
            st.write(f"**Regra de aprovação:** {f['regra']}")
            for coluna, (rotulo, valor) in zip(st.columns(len(f["numeros"])), f["numeros"]):
                coluna.metric(rotulo, valor)
            st.write(f"**Por que não passou:** {f['por_que']}")
            st.write(f"**O que aprendemos:** {f['aprendizado']}")
