import numpy as np
from sklearn.metrics import average_precision_score, precision_score, recall_score, f1_score, confusion_matrix


def evaluate(y, probability, threshold=.5):
    predicted = np.asarray(probability) >= threshold
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    return {"precision": float(precision_score(y, predicted, zero_division=0)),
            "recall": float(recall_score(y, predicted, zero_division=0)),
            "f1": float(f1_score(y, predicted, zero_division=0)),
            "pr_auc_average_precision": float(average_precision_score(y, probability)),
            "false_alarm_rate": float(fp / (fp + tn)) if fp + tn else None,
            "threshold": threshold, "examples": len(y), "positives": int(np.sum(y)),
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}}
