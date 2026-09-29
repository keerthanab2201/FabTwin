"""SQLite event history, twins, and alert episodes in one atomic transaction."""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from streaming.schema import Telemetry
from streaming.feature_engine import features
from streaming.anomaly_detector import Predictor


class StateManager:
    def __init__(self, path="data/fabtwin.db", model_path="artifacts/equipment.joblib"):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.predictor = Predictor(model_path)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS telemetry (
                event_id TEXT PRIMARY KEY, machine_id TEXT NOT NULL, run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL, timestamp_ms INTEGER NOT NULL, received_ms INTEGER NOT NULL,
                payload TEXT NOT NULL, UNIQUE(machine_id, run_id, sequence));
            CREATE INDEX IF NOT EXISTS history ON telemetry(machine_id, timestamp_ms DESC);
            CREATE TABLE IF NOT EXISTS twins(machine_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS alerts(
                id INTEGER PRIMARY KEY, machine_id TEXT NOT NULL, kind TEXT NOT NULL,
                created_ms INTEGER NOT NULL, resolved_ms INTEGER, message TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS active_alert ON alerts(machine_id,kind) WHERE resolved_ms IS NULL;
            CREATE TABLE IF NOT EXISTS rejected(id INTEGER PRIMARY KEY, received_ms INTEGER, reason TEXT, payload TEXT);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def reject(self, payload, reason):
        with self.connect() as db:
            db.execute("INSERT INTO rejected(received_ms,reason,payload) VALUES(?,?,?)", (int(time.time()*1000), reason, payload))

    def ingest(self, raw):
        event = Telemetry.model_validate(raw).model_dump()
        now = int(time.time() * 1000)
        if event["timestamp_ms"] > now + 60_000:
            raise ValueError("event timestamp exceeds allowed clock skew")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute("INSERT OR IGNORE INTO telemetry VALUES(?,?,?,?,?,?,?)", (
                event["event_id"], event["machine_id"], event["run_id"], event["sequence"], event["timestamp_ms"], now, json.dumps(event)))
            if cursor.rowcount == 0:
                return {"status": "duplicate"}
            old_row = db.execute("SELECT payload FROM twins WHERE machine_id=?", (event["machine_id"],)).fetchone()
            old = json.loads(old_row[0]) if old_row else None
            if old and ((old["run_id"] == event["run_id"] and old["sequence"] >= event["sequence"]) or
                        old["timestamp_ms"] > event["timestamp_ms"]):
                return {"status": "historical"}
            rows = db.execute("SELECT payload FROM telemetry WHERE machine_id=? AND run_id=? AND sequence<=? AND timestamp_ms>=? ORDER BY sequence DESC LIMIT 300",
                (event["machine_id"], event["run_id"], event["sequence"], event["timestamp_ms"]-300_000)).fetchall()
            vector = features([json.loads(row[0]) for row in reversed(rows)])
            twin = {**event, **self.predictor.score(event, vector), "last_updated": now}
            db.execute("INSERT OR REPLACE INTO twins VALUES(?,?)", (event["machine_id"], json.dumps(twin)))
            kind = None
            if event["state"] == "FAULT":
                kind = "equipment_fault"
            elif event["state"] in ("RUNNING", "DEGRADING"):
                if (twin["failure_probability"] or 0) > .8:
                    kind = "maintenance_required"
                elif (twin["anomaly_score"] or 0) > .99 or twin["primary_deviations"]:
                    kind = "inspection_required"
            # Hysteresis: resolve after maintenance or a genuinely healthy reading.
            if event["state"] == "MAINTENANCE" or (kind is None and twin["health_score"] >= 90 and (twin["failure_probability"] or 0) < .3 and (twin["anomaly_score"] or 0) < .95):
                db.execute("UPDATE alerts SET resolved_ms=? WHERE machine_id=? AND resolved_ms IS NULL", (now, event["machine_id"]))
            if kind:
                db.execute("INSERT OR IGNORE INTO alerts(machine_id,kind,created_ms,message) VALUES(?,?,?,?)",
                    (event["machine_id"], kind, now, "; ".join(twin["primary_deviations"]) or event["state"]))
            return {"status": "updated", "twin": twin}

    def machines(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM twins ORDER BY machine_id")]

    def machine(self, machine_id):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM twins WHERE machine_id=?", (machine_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def history(self, machine_id, limit=300):
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM telemetry WHERE machine_id=? ORDER BY timestamp_ms DESC, sequence DESC LIMIT ?", (machine_id, limit)).fetchall()
            return [json.loads(row[0]) for row in reversed(rows)]

    def alerts(self, machine_id=None):
        with self.connect() as db:
            query = "SELECT * FROM alerts" + (" WHERE machine_id=?" if machine_id else "") + " ORDER BY id DESC LIMIT 200"
            return [dict(row) for row in db.execute(query, (machine_id,) if machine_id else ())]

    def metrics(self):
        with self.connect() as db:
            count = db.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0]
            latencies = sorted(row[0] for row in db.execute("SELECT received_ms-timestamp_ms FROM telemetry ORDER BY received_ms DESC LIMIT 10000"))
            return {"events_processed": count, "p95_ingestion_latency_ms": latencies[min(len(latencies)-1, int(.95*len(latencies)))] if latencies else None,
                    "latency_sample_count": len(latencies), "rejected_events": db.execute("SELECT COUNT(*) FROM rejected").fetchone()[0]}
