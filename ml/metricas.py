"""Métricas da classe "dia crítico". A acurácia não serve: dias críticos são ~5%."""

from sklearn.metrics import f1_score, precision_score, recall_score


def resumo(real, previsto):
    real, previsto = list(map(bool, real)), list(map(bool, previsto))
    return {"recall": round(recall_score(real, previsto, zero_division=0), 3),
            "precisao": round(precision_score(real, previsto, zero_division=0), 3),
            "f1": round(f1_score(real, previsto, zero_division=0), 3),
            "alertas": sum(previsto), "criticos": sum(real)}


def texto(nome, m):
    return (f"{nome:<28} recall {m['recall']:.0%} | precisão {m['precisao']:.0%} | F1 {m['f1']:.2f} "
            f"| {m['alertas']} alertas para {m['criticos']} dias críticos")
