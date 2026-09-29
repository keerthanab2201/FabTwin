import time
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app
from digital_twin.state_manager import StateManager
from streaming.feature_engine import features, FEATURE_NAMES
from streaming.consumer import process
from ml.train_equipment import build_dataset


def event(sequence=0, **changes):
    data = dict(event_id=f"run:ETCHER_1:{sequence}", machine_id="ETCHER_1", run_id="run", sequence=sequence,
                timestamp_ms=int(time.time()*1000)+sequence, state="RUNNING", temperature=70., pressure=4.2,
                vibration=.2, power=238., flow_rate=12.7, cycle_time=30., error_code=0)
    data.update(changes)
    return data


@pytest.fixture
def store(tmp_path):
    return StateManager(tmp_path / "test.db", model_path=None)


def test_duplicate_and_out_of_order_do_not_regress_twin(store):
    newer = event(5)
    assert store.ingest(newer)["status"] == "updated"
    assert store.ingest(newer)["status"] == "duplicate"
    assert store.ingest(event(2))["status"] == "historical"
    assert store.machine("ETCHER_1")["sequence"] == 5
    assert store.metrics()["events_processed"] == 2


def test_alert_dedup_survives_restart_and_rearms_after_maintenance(store):
    store.ingest(event(0, vibration=.5))
    restarted = StateManager(store.path, model_path=None)
    restarted.ingest(event(1, vibration=.52))
    assert len(restarted.alerts()) == 1
    restarted.ingest(event(2, state="MAINTENANCE"))
    assert restarted.alerts()[0]["resolved_ms"] is not None
    restarted.ingest(event(3, vibration=.5))
    assert len(restarted.alerts()) == 2


def test_invalid_data_is_quarantined(store):
    process(store, '{"vibration":NaN}')
    assert store.metrics()["rejected_events"] == 1
    assert store.metrics()["events_processed"] == 0
    with pytest.raises(ValueError):
        store.ingest(event(temperature=float("inf")))


def test_new_run_and_delayed_old_run(store):
    timestamp = int(time.time()*1000)
    store.ingest(event(100, timestamp_ms=timestamp-1000))
    store.ingest(event(0, event_id="new:0", run_id="new", timestamp_ms=timestamp))
    assert store.ingest(event(101, timestamp_ms=timestamp-900))["status"] == "historical"
    assert store.machine("ETCHER_1")["run_id"] == "new"


def test_window_has_correct_slope_and_expiry():
    rows = [event(0, vibration=10., timestamp_ms=1000), event(1, vibration=.2, timestamp_ms=400000), event(2, vibration=.4, timestamp_ms=401000)]
    vector = features(rows)
    assert vector[FEATURE_NAMES.index("vibration_mean")] == pytest.approx(.3)
    assert vector[FEATURE_NAMES.index("vibration_slope")] == pytest.approx(.2)


def test_labels_use_observed_future_and_exclude_censoring():
    rows = [event(i, state="FAULT" if i==5 else "RUNNING") for i in range(6)]
    x, labels, _, _ = build_dataset(rows, 2)
    assert labels.tolist() == [0, 0, 0, 1]
    assert len(x) == 4


def test_api_contract_and_missing_machine(store):
    store.ingest(event())
    client = TestClient(create_app(store.path))
    assert client.get("/healthz").status_code == 200
    assert len(client.get("/machines").json()) == 1
    assert client.get("/machines/ETCHER_1/health").json()["failure_probability"] is None
    assert len(client.get("/machines/ETCHER_1/telemetry").json()) == 1
    assert client.get("/machines/MISSING/alerts").status_code == 404
    assert client.get("/machines/ETCHER_1/telemetry?limit=99999").status_code == 422
