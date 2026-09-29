import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from digital_twin.state_manager import StateManager


def create_app(db_path=None):
    app = FastAPI(title="FabTwin", version="0.1.0")
    store = StateManager(db_path or os.getenv("FABTWIN_DB", "data/fabtwin.db"))

    def require(machine_id):
        machine = store.machine(machine_id)
        if machine is None:
            raise HTTPException(404, "Machine not found")
        return machine

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/machines")
    def machines():
        return store.machines()

    @app.get("/machines/{machine_id}")
    def machine(machine_id: str):
        return require(machine_id)

    @app.get("/machines/{machine_id}/health")
    def health(machine_id: str):
        item = require(machine_id)
        return {key: item[key] for key in ("machine_id", "health_score", "failure_probability", "anomaly_score", "primary_deviations", "prediction_source", "prediction_horizon_cycles")}

    @app.get("/machines/{machine_id}/telemetry")
    def telemetry(machine_id: str, limit: int = Query(300, ge=1, le=2000)):
        require(machine_id)
        return store.history(machine_id, limit)

    @app.get("/machines/{machine_id}/alerts")
    def alerts(machine_id: str):
        require(machine_id)
        return store.alerts(machine_id)

    @app.get("/alerts")
    def all_alerts():
        return store.alerts()

    @app.get("/metrics")
    def metrics():
        return store.metrics()

    @app.get("/process/report")
    def process_report():
        import json
        path = Path("artifacts/secom-report.json")
        return json.loads(path.read_text()) if path.exists() else {"status": "not_trained", "source": "UCI SECOM", "message": "Run python -m ml.train_secom with downloaded SECOM files."}

    if Path("frontend/dist").exists():
        app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="dashboard")
    return app


app = create_app()
