"""Classificador de dia crítico: árvore de decisão ou XGBoost, no roteiro da AVD.

    otimizar()        GridSearchCV com validação POR TEMPO (TimeSeriesSplit), só no treino
    escolher_limiar() o corte de probabilidade escolhido num ano de validação (o último
                      do treino), nunca no teste: o de menos alarmes falsos entre os que
                      avisam pelo menos 80% dos dias críticos
    treinar()         ajusta com os melhores parâmetros no treino inteiro
    prever()          probabilidade e decisão (acima do limiar = dia crítico)
    salvar/carregar   joblib em modelos/ (fora do Git)

O XGBoost aceita entradas vazias (dia sem chuva medida) sem precisar inventar valor.
"""

from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.base import clone
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.tree import DecisionTreeClassifier
from xgboost import XGBClassifier

# Ficam de fora dia da semana, fim de semana, feriado e pandemia: ensinavam a ROTINA da
# Defesa Civil (quando ela registra), não o efeito da chuva (decisão 009, revisada).
ENTRADAS = [
    "chuva_dia_mm", "chuva_vespera_mm", "chuva_3d_mm", "chuva_7d_mm", "acumulado_72h_antes", "max_hora_mm",
    "mare_max_m", "mare_amplitude_m",
    "mes", "distrito_codigo",
]
# Também ficam de fora população, comunidades e áreas de risco: são fixas por distrito, ou
# seja, repetem o distrito_codigo e só embaralhavam a leitura da importância das entradas.

# Para o teste "sem chuva": o mesmo modelo só com distrito, mês e maré. Se ele for quase tão bom
# quanto o completo, quem prevê é o calendário, não a chuva.
CHUVA = ["chuva_dia_mm", "chuva_vespera_mm", "chuva_3d_mm", "chuva_7d_mm", "acumulado_72h_antes", "max_hora_mm"]
SEM_CHUVA = [e for e in ENTRADAS if e not in CHUVA]
PASTA = Path(__file__).resolve().parents[1] / "modelos"
META_RECALL = 0.80  # a meta do projeto: avisar pelo menos 8 de cada 10 dias críticos

GRADES = {
    "arvore": {"max_depth": [3, 5, 8, 12], "min_samples_leaf": [20, 50, 100]},
    "xgboost": {"n_estimators": [200, 400], "max_depth": [3, 5], "learning_rate": [0.05, 0.1]},
}


def matriz(df, entradas=None):
    """Entradas como números (booleanos viram 0/1; vazio continua vazio)."""
    return df[entradas or ENTRADAS].astype(float)


class ModeloRisco:
    def __init__(self, tipo="xgboost", grade=None, entradas=None):
        if tipo not in GRADES:
            raise ValueError(f"tipo deve ser um de {list(GRADES)}")
        self.tipo, self.grade = tipo, grade or GRADES[tipo]
        self.entradas = list(entradas or ENTRADAS)
        self.estimador = self.melhores = None
        self.limiar = 0.5

    def _base(self, y):
        if self.tipo == "arvore":
            return DecisionTreeClassifier(class_weight="balanced", random_state=42)
        positivos = max(1, int(np.sum(y)))
        return XGBClassifier(objective="binary:logistic", eval_metric="aucpr", tree_method="hist",
                             subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=-1,
                             scale_pos_weight=(len(y) - positivos) / positivos)  # compensa os dias raros

    def otimizar(self, X, y, divisoes=4):
        """Hiperparâmetros por validação cruzada no tempo: cada dobra treina no passado e valida no futuro."""
        # no Windows, o XGBoost quebra em vários processos ao mesmo tempo: ele já usa todos os
        # núcleos sozinho, então a busca roda um treino por vez
        busca = GridSearchCV(self._base(y), self.grade, scoring="average_precision",
                             cv=TimeSeriesSplit(n_splits=divisoes), n_jobs=1 if self.tipo == "xgboost" else -1)
        busca.fit(X, y)
        self.melhores = busca.best_params_
        return busca.best_score_

    def escolher_limiar(self, X_tr, y_tr, X_val, y_val, meta_recall=META_RECALL):
        """Corte de probabilidade escolhido no ano de validação (nunca no teste).

        O pior caso para a cliente é o evento NÃO avisado: entre os cortes que pegam pelo
        menos `meta_recall` dos dias críticos, fica o de menos alarmes falsos (maior precisão).
        Se nenhum chega à meta, fica o de melhor F1.
        """
        modelo = clone(self._base(y_tr)).set_params(**(self.melhores or {}))
        modelo.fit(X_tr, y_tr)
        proba = modelo.predict_proba(X_val)[:, 1]
        candidatos = np.unique(np.quantile(proba, np.linspace(0.0, 0.999, 300)))
        y_val = np.asarray(y_val, dtype=bool)
        avaliados = []
        for c in candidatos:
            previsto = proba >= c
            avaliados.append((c, recall_score(y_val, previsto, zero_division=0),
                              precision_score(y_val, previsto, zero_division=0),
                              f1_score(y_val, previsto, zero_division=0)))
        na_meta = [a for a in avaliados if a[1] >= meta_recall]
        escolhido = max(na_meta, key=lambda a: (a[2], a[0])) if na_meta else max(avaliados, key=lambda a: a[3])
        self.limiar = float(escolhido[0])
        self.validacao = {"recall": round(escolhido[1], 3), "precisao": round(escolhido[2], 3),
                          "f1": round(escolhido[3], 3), "atingiu_meta": bool(na_meta)}
        return self.limiar, escolhido[3]

    def treinar(self, X, y):
        self.estimador = clone(self._base(y)).set_params(**(self.melhores or {}))
        self.estimador.fit(X, y)
        return self

    def probabilidade(self, X):
        return self.estimador.predict_proba(X)[:, 1]

    def prever(self, X):
        return self.probabilidade(X) >= self.limiar

    def importancia(self):
        return dict(sorted(zip(self.entradas, map(float, self.estimador.feature_importances_)), key=lambda p: -p[1]))

    def salvar(self, nome="risco", extras=None):
        PASTA.mkdir(exist_ok=True)
        caminho = PASTA / f"{nome}.joblib"
        joblib.dump({"tipo": self.tipo, "estimador": self.estimador, "limiar": self.limiar,
                     "melhores": self.melhores, "entradas": self.entradas,
                     "treinado_em": datetime.now(timezone.utc).isoformat(), **(extras or {})}, caminho)
        return caminho

    @classmethod
    def carregar(cls, nome="risco"):
        pacote = joblib.load(PASTA / f"{nome}.joblib")
        if pacote["entradas"] != ENTRADAS:
            raise ValueError("o modelo salvo usa outras entradas: treine de novo (python -m ml.treinar)")
        m = cls(pacote["tipo"])
        m.estimador, m.limiar, m.melhores = pacote["estimador"], pacote["limiar"], pacote["melhores"]
        m.pacote = pacote
        return m
