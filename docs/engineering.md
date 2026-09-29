# FabTwin

C++17 edge telemetry, persistent equipment digital twins, predictive maintenance, and independent semiconductor process analysis. This is a local engineering prototype using controlled simulated equipment, not a validated model of physical fab equipment.

## Architecture

```text
24 simulated machines (etcher / deposition / inspection / cleaner)
  -> C++ collection thread
  -> bounded raw FIFO
  -> preprocessing thread (validation, rolling mean, threshold checks)
  -> bounded publishing FIFO
  -> publisher thread (retry retained event until acknowledgment)
  -> Kafka, keyed by machine ID
  -> Python consumer (causal rolling features + RF / Isolation Forest)
  -> SQLite event history + latest twin + deduplicated alert episodes
  -> FastAPI -> React dashboard

UCI SECOM -> median imputation -> variance filter -> feature selection
          -> balanced logistic regression -> independent yield report
```

For local development, JSONL pipes replace Kafka while using the same compiled C++ edge and Python processing code. Kafka is implemented through librdkafka in the edge and confluent-kafka in Python. Docker Compose defines the complete broker-based path.

## Run locally on Windows

Use Python 3.10+, Node 22+, and a C++17 compiler with `std::thread` support. The installed legacy `C:\MinGW` compiler does not provide it; the included build script prefers MSYS2 MinGW-w64 when present.

From the repository directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e '.[test]'
.\scripts\build_edge.ps1
cd frontend
npm ci
npm run build
cd ..
```

Terminal 1 (API and built dashboard):

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Terminal 2 (live C++ simulation and Python processing):

```powershell
python scripts/local_demo.py
```

Open <http://127.0.0.1:8000> for the dashboard and <http://127.0.0.1:8000/docs> for API documentation. Stop the demo with Ctrl+C. `--ticks 60` gives a finite run which drains its queues. Force-stopping a continuous run does not drain its in-memory backlog.

Linux / macOS edge build:

```sh
cmake -S edge -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
python scripts/local_demo.py --edge build/fabtwin-edge
```

For frontend development, `npm run dev` in `frontend` proxies API routes to port 8000.

## Train equipment models

Generate training data directly from the C++ simulator. The Python command avoids PowerShell output encoding differences:

```powershell
python -c "import subprocess; f=open('data/equipment.jsonl','w',encoding='utf-8'); subprocess.run(['build/fabtwin-edge.exe','--machines','24','--ticks','480','--interval-ms','0'],stdout=f,check=True); f.close()"
python -m ml.train_equipment data/equipment.jsonl
```

On Linux, use `build/fabtwin-edge` as the executable. Models are saved to `artifacts/equipment.joblib`; evaluation is in `artifacts/equipment.json`. Restart the consumer after retraining. Only load trusted local joblib artifacts.

Features comprise mean, standard deviation, maximum and per-cycle linear slope for six sensors. Windows contain at most 300 readings from the preceding five event-time minutes. This is a capped time window, not a guarantee of a full five-minute history. Features never contain machine state, error code, future sensor values, or simulator degradation fraction. The label is an observed fault within the next 20 operating cycles, and examples without a complete future horizon are excluded. Whole machine IDs are held out to avoid adjacent-window train/test leakage. The deterministic simulator remains an easy, synthetic environment; the test does not establish real-world generalization.

Logistic Regression and Random Forest are evaluated; Random Forest is the preselected serving model. Isolation Forest is fitted on normal training windows with a separate subset used for an empirical anomaly percentile. That percentile is not a failure probability. Failure predictions apply only to RUNNING/DEGRADING states. Missing models produce null predictions, not invented probabilities. Health score is an explicit sensor heuristic. Signal deviations are threshold observations, not causal explanations of model predictions.

## Train the separate SECOM process model

```powershell
python scripts/download_secom.py
python -m ml.train_secom data/secom
```

Source: [UCI SECOM](https://archive.ics.uci.edu/dataset/179/secom), McCann & Johnston, DOI `10.24432/C54305`. Preserve source attribution and review the dataset license before redistribution. The downloaded numeric file has **1,567 rows and 590 process columns**; UCI's prose describes 591 features. The code reports the observed shape rather than assigning physical meaning to anonymized columns. Missing data, imputation, scaling, variance filtering and selection are fitted on training data only. The final 20% by timestamp is held out; post-hoc permutation importance does not feed model selection. The dashboard displays the saved process evaluation report, not live SECOM streaming.

## API

| Route | Purpose |
|---|---|
| `GET /machines` | Latest persisted machine twins |
| `GET /machines/{id}` | One machine |
| `GET /machines/{id}/health` | Health, predictions, deviations |
| `GET /machines/{id}/telemetry?limit=300` | Recent ordered history; max 2,000 |
| `GET /machines/{id}/alerts` | Alert and resolution history |
| `GET /alerts` | Latest 200 alerts |
| `GET /metrics` | Event count, latest 10,000 events' p95 ingestion lag, rejected count |
| `GET /process/report` | SECOM evaluation or explicit not-trained status |
| `GET /healthz` | API liveness |

Twins and alert episodes update atomically with event persistence. Event identity and `(machine, run, sequence)` uniqueness make consumer replay idempotent. Older events remain in history but do not regress the twin. Kafka offsets commit synchronously after the SQLite transaction. Invalid payloads are persisted in the rejected table before acknowledging their Kafka offsets. Storage failures propagate and prevent offset commit.

## Docker / Kafka

Start Docker Desktop, then:

```powershell
docker compose up --build
```

The API binds to localhost:8000. Kafka stays inside the Compose network. The topic has three partitions and machine IDs are message keys. One broker / replication factor one is a development setup, not a highly available cluster. Kafka 3.9.1 uses the [official Apache image](https://kafka.apache.org/39/getting-started/quickstart/). Artifacts and SQLite storage are mounted from the local project.

To exercise a real broker outage after startup, stop Kafka with `docker compose stop kafka`, wait 30 seconds, then `docker compose start kafka`. Inspect edge/consumer logs and persisted sequence continuity. The provided automated benchmark below injects transport unavailability in the C++ publisher and uses a JSONL sink; it does not perform this broker integration test.

## Verification and honest measurements

```powershell
python -m pytest -q
python scripts/benchmark.py build/fabtwin-edge.exe
```

The benchmark generates 100 devices × 300 readings at 100 ms per collection cycle, injects a 30-second publishing outage, then verifies received event count, uniqueness and contiguous per-machine ordering. It writes `artifacts/outage-report.json`. Tests also force queue capacities of one and ten to exercise blocking/backpressure.

Measured during initial implementation:

| Evaluation | Result |
|---|---|
| C++ simulated 30-second outage, JSONL sink | 30,000 received / 30,000 generated, zero loss, ordered per machine |
| RF, held-out simulated machines, threshold 0.8 | Precision 0.9953; recall 0.7071; F1 0.8268; average precision 0.9553; false-alarm rate 0.000384 |
| SECOM chronological holdout, threshold 0.5 | Precision 0.1067; recall 0.4706; F1 0.1739; average precision 0.1704; false-alarm rate 0.2256 |

The SECOM result is a baseline with a high false-alarm rate, not a production-ready yield predictor. Its holdout contains only 17 failures among 314 examples. Equipment metrics describe controlled simulated data only. Average precision is the PR summary used here, not trapezoidal PR area. Full raw reports are in `artifacts/` and are generated locally rather than committed.

## Current limits and next engineering work

- The edge buffer is bounded **RAM**, not a durable disk spool. It survives transport unavailability while the process stays alive; process crashes or power loss can lose queued events. A full queue pauses simulation instead of silently discarding readings.
- Publishing waits for each broker acknowledgment. This intentionally prioritizes simple ordered recovery over throughput; do not claim 5,000 events/sec from this implementation without measuring the actual Kafka path.
- Docker/Kafka integration has not been run in the initial environment because the Docker daemon was unavailable. The Kafka-enabled C++ build also needs validation there.
- End-to-end throughput, recovery-only duration and alert detection latency are not benchmarked yet. API ingestion lag includes replay delay and depends on synchronized clocks; it is not processing-only latency.
- History/rejected-event retention is unbounded. Add retention, durable edge spooling, graceful signal-driven drain, operational monitoring, and authentication before deployment beyond localhost.
- The four machine types share simplified sensor equations and randomized noise. State changes follow controlled episodes, not calibrated fab physics. Maintenance transitions are simulated, not operator work orders.
- SECOM threshold tuning should use a separate training/validation split, with a final untouched test period. Calibration, temporal drift checks and real-equipment validation remain future work.
