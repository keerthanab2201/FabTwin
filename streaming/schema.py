from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Telemetry(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    event_id: str = Field(min_length=1, max_length=200)
    machine_id: str = Field(pattern=r"^[A-Z]+_[0-9]+$", max_length=60)
    run_id: str = Field(min_length=1, max_length=100)
    sequence: int = Field(ge=0)
    timestamp_ms: int = Field(gt=0)
    state: Literal["IDLE", "RUNNING", "DEGRADING", "FAULT", "MAINTENANCE"]
    temperature: float = Field(ge=-50, le=300)
    pressure: float = Field(gt=0, le=100)
    vibration: float = Field(ge=0, le=20)
    power: float = Field(ge=0, le=10000)
    flow_rate: float = Field(ge=0, le=1000)
    cycle_time: float = Field(gt=0, le=10000)
    error_code: int = Field(ge=0)
    edge_vibration_mean: float = 0
    edge_anomaly: bool = False
