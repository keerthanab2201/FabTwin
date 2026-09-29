"""Shared causal features, limited to five event-time minutes and 300 readings."""
import numpy as np

SENSORS = ("temperature", "pressure", "vibration", "power", "flow_rate", "cycle_time")
FEATURE_NAMES = [f"{sensor}_{stat}" for sensor in SENSORS for stat in ("mean", "std", "max", "slope")]


def features(events):
    latest = events[-1]
    window = [e for e in events[-300:] if e["timestamp_ms"] >= latest["timestamp_ms"] - 300_000]
    # Per operating cycle, independent of accelerated simulation wall-clock rate.
    x = np.asarray([e["sequence"] for e in window], dtype=float)
    x -= x.mean()
    denominator = float(x @ x)
    result = []
    for sensor in SENSORS:
        values = np.asarray([e[sensor] for e in window], dtype=float)
        slope = float(x @ (values - values.mean()) / denominator) if denominator else 0.0
        result.extend([float(values.mean()), float(values.std()), float(values.max()), slope])
    return result
