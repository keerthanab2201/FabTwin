"""Train on simulator JSONL; hold out entire machines, never overlapping windows."""
import argparse
import json
from collections import defaultdict
from pathlib import Path
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from streaming.feature_engine import features, FEATURE_NAMES
from streaming.schema import Telemetry
from ml.evaluate import evaluate


def build_dataset(events, horizon):
    grouped = defaultdict(list)
    for event in events:
        event = Telemetry.model_validate(event).model_dump()
        grouped[(event["machine_id"], event["run_id"])].append(event)
    x, y, groups, normal = [], [], [], []
    for (machine, _), rows in grouped.items():
        rows.sort(key=lambda e: e["sequence"])
        for index, event in enumerate(rows):
            if event["state"] not in ("RUNNING", "DEGRADING"):
                continue
            future = rows[index + 1:index + horizon + 1]
            # Require contiguous observed future; exclude right-censored examples.
            if len(future) < horizon or future[-1]["sequence"] != event["sequence"] + horizon:
                continue
            label = int(any(e["state"] == "FAULT" for e in future))
            x.append(features(rows[max(0, index-299):index+1]))
            y.append(label)
            groups.append(machine)
            normal.append(event["state"] == "RUNNING" and not label)
    return np.asarray(x), np.asarray(y), np.asarray(groups), np.asarray(normal)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("artifacts/equipment.joblib"))
    args = parser.parse_args()
    if args.horizon < 1:
        parser.error("horizon must be positive")
    events = [json.loads(line) for line in args.input.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    x, y, groups, normal = build_dataset(events, args.horizon)
    if len(set(groups)) < 4 or len(set(y)) < 2:
        raise ValueError("Generate at least four machines with complete degradation episodes")
    train, test = next(GroupShuffleSplit(n_splits=1, test_size=.3, random_state=42).split(x, y, groups))
    if any(len(set(y[indices])) < 2 for indices in (train, test)):
        raise ValueError("Both splits must contain failures and normal examples")
    models = {
        "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=2000, random_state=42)),
        "random_forest": RandomForestClassifier(n_estimators=100, max_depth=8, min_samples_leaf=5, class_weight="balanced", random_state=42, n_jobs=-1)}
    reports = {}
    for name, model in models.items():
        model.fit(x[train], y[train])
        reports[name] = evaluate(y[test], model.predict_proba(x[test])[:, 1], threshold=.8)
    normal_train = x[train][normal[train]]
    # Separate normal calibration examples from Isolation Forest fitting examples.
    cut = max(1, int(.8 * len(normal_train)))
    anomaly = IsolationForest(n_estimators=100, contamination=.01, random_state=42, n_jobs=-1).fit(normal_train[:cut])
    normal_scores = np.sort(-anomaly.score_samples(normal_train[cut:]))
    report = {"source": "controlled_cpp_simulator", "horizon_cycles": args.horizon,
              "split": "held_out_machines", "train_machines": sorted(set(groups[train])), "test_machines": sorted(set(groups[test])),
              "models": reports, "selected_model": "random_forest (preselected, not chosen by test results)",
              "limitation": "Deterministic simulated degradation; these results do not estimate performance on real equipment."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"failure": models["random_forest"], "anomaly": anomaly, "normal_scores": normal_scores,
                 "feature_names": FEATURE_NAMES, "horizon": args.horizon}, args.output)
    args.output.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
