"""Independent process/yield model. Anonymous columns are never equipment sensors."""
import argparse
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.feature_selection import VarianceThreshold, SelectKBest, f_classif
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.inspection import permutation_importance
from ml.evaluate import evaluate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path, help="Directory containing secom.data and secom_labels.data")
    args = parser.parse_args()
    x = pd.read_csv(args.directory / "secom.data", sep=r"\s+", header=None)
    labels = pd.read_csv(args.directory / "secom_labels.data", sep=r"\s+", header=None)
    y = (labels[0].to_numpy() == 1).astype(int)
    dates = pd.to_datetime(labels[1], dayfirst=True)
    order = np.argsort(dates.to_numpy(), kind="stable")
    cut = int(.8 * len(order))
    train, test = order[:cut], order[cut:]
    model = Pipeline([("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                      ("variance", VarianceThreshold()), ("scale", StandardScaler()),
                      ("select", SelectKBest(f_classif, k=40)),
                      ("classifier", LogisticRegression(class_weight="balanced", max_iter=3000, C=.1, random_state=42))])
    model.fit(x.iloc[train], y[train])
    probability = model.predict_proba(x.iloc[test])[:, 1]
    # Post-hoc interpretation only; held-out importance does not feed model selection.
    importance = permutation_importance(model, x.iloc[test], y[test], scoring="average_precision", n_repeats=3, random_state=42)
    top = np.argsort(importance.importances_mean)[-10:][::-1]
    report = {"status": "trained", "source": "UCI SECOM", "source_url": "https://archive.ics.uci.edu/dataset/179/secom",
              "rows": len(x), "observed_process_columns": x.shape[1], "missing_fraction": float(x.isna().mean().mean()),
              "split": "chronological first 80% train / last 20% test", "metrics": evaluate(y[test], probability),
              "top_process_signals": [{"feature": f"process_{i:03d}", "pr_auc_decrease": float(importance.importances_mean[i])} for i in top],
              "limitation": "Anonymized process signals; associations are not physical sensor identities or causal effects. Default threshold 0.5, no test-set tuning."}
    Path("artifacts").mkdir(exist_ok=True)
    joblib.dump(model, "artifacts/secom.joblib")
    Path("artifacts/secom-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
