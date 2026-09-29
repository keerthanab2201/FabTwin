from pathlib import Path
import joblib
import numpy as np
from streaming.feature_engine import FEATURE_NAMES


class Predictor:
    def __init__(self, path="artifacts/equipment.joblib"):
        # Only load locally trained/trusted artifacts: joblib is executable serialization.
        self.bundle = joblib.load(path) if path and Path(path).exists() else None
        if self.bundle and self.bundle["feature_names"] != FEATURE_NAMES:
            raise ValueError("Model feature schema mismatch")
        if self.bundle:
            self.bundle["failure"].set_params(n_jobs=1)
            self.bundle["anomaly"].set_params(n_jobs=1)

    def score(self, event, vector):
        deviations = []
        if event["vibration"] > 0.32:
            deviations.append("Elevated vibration")
        if event["temperature"] > 79:
            deviations.append("Elevated temperature")
        if vector[FEATURE_NAMES.index("pressure_std")] > 0.10:
            deviations.append("Unstable pressure")
        risk = None
        anomaly = None
        if self.bundle and event["state"] in ("RUNNING", "DEGRADING"):
            risk = float(self.bundle["failure"].predict_proba([vector])[0, 1])
            # Empirical percentile against normal validation scores; not a probability.
            raw = float(-self.bundle["anomaly"].score_samples([vector])[0])
            reference = self.bundle["normal_scores"]
            anomaly = float(np.searchsorted(reference, raw, side="right") / len(reference))
        health = max(0, min(100, round(100 - max(0, event["vibration"] - .2) * 140 - max(0, event["temperature"] - 70) * 1.4)))
        if event["state"] == "FAULT":
            health = 0
        return {"health_score": health, "failure_probability": risk, "anomaly_score": anomaly,
                "prediction_source": "trained_simulator_model" if risk is not None else "unavailable",
                "prediction_horizon_cycles": self.bundle["horizon"] if self.bundle else None,
                "primary_deviations": deviations,
                "predicted_failure": "simulated_degradation" if risk is not None and risk > .8 else None}
