import json
import subprocess
from pathlib import Path
import pytest


@pytest.mark.parametrize("capacity", [1, 10])
def test_cpp_outage_backpressure_order_and_state_lifecycle(capacity):
    executable = next((p for p in (Path("build/fabtwin-edge.exe"), Path("build/fabtwin-edge")) if p.exists()), None)
    if executable is None:
        pytest.skip("Build C++ edge first")
    result = subprocess.run([str(executable.resolve()), "--machines", "4", "--ticks", "250", "--interval-ms", "0", "--capacity", str(capacity), "--outage-ms", "150"], capture_output=True, text=True, check=True, timeout=30)
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(events) == 1000
    assert len({e["event_id"] for e in events}) == 1000
    for machine in {e["machine_id"] for e in events}:
        rows = [e for e in events if e["machine_id"] == machine]
        assert [e["sequence"] for e in rows] == list(range(250))
    etcher = [e for e in events if e["machine_id"] == "ETCHER_1"]
    assert {e["state"] for e in etcher} == {"IDLE", "RUNNING", "DEGRADING", "FAULT", "MAINTENANCE"}
    assert etcher[185]["vibration"] > etcher[115]["vibration"]
    assert etcher[240]["state"] == "RUNNING"
    assert json.loads(result.stderr)["retry_attempts"] > 0
