"""Exercise real compiled C++ collection, bounded queues and outage replay."""
import argparse
import json
import subprocess
import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from digital_twin.state_manager import StateManager

parser = argparse.ArgumentParser()
parser.add_argument("executable")
parser.add_argument("--outage-ms", type=int, default=30000)
parser.add_argument("--machines", type=int, default=100)
parser.add_argument("--ticks", type=int, default=300)
parser.add_argument("--interval-ms", type=int, default=100)
parser.add_argument("--capacity", type=int, default=65536)
args = parser.parse_args()
started = time.perf_counter()
result = subprocess.run([args.executable, "--machines", str(args.machines), "--ticks", str(args.ticks), "--interval-ms", str(args.interval_ms),
                         "--outage-ms", str(args.outage_ms), "--capacity", str(args.capacity)], capture_output=True, text=True, check=True, timeout=max(120, args.outage_ms/1000+args.ticks*args.interval_ms/1000+60))
elapsed = time.perf_counter() - started
events = [json.loads(line) for line in result.stdout.splitlines()]
expected = args.machines * args.ticks
assert len(events) == expected, (len(events), expected)
assert len({event["event_id"] for event in events}) == expected
sequences = {}
for event in events:
    last = sequences.get(event["machine_id"], -1)
    assert event["sequence"] == last + 1
    sequences[event["machine_id"]] = event["sequence"]
Path("artifacts").mkdir(exist_ok=True)
report = {"scope": "C++ edge to JSONL sink, simulated transport unavailability; not a Kafka or end-to-end benchmark",
          "outage_ms": args.outage_ms, "events_expected": expected, "events_received": len(events), "events_lost": expected-len(events),
          "ordered_per_machine": True, "elapsed_seconds": elapsed, "events_per_second_including_outage": len(events)/elapsed,
          "edge_metrics": json.loads(result.stderr.strip().splitlines()[-1]), "queue_capacity_each": args.capacity,
          "limitation": "In-memory buffering survives transport outages only, not process or host failure. Backpressure may pause simulation."}
Path("artifacts/outage-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
