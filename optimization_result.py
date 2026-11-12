"""Serializable record of one optimizer invocation."""

from dataclasses import dataclass, field
import json
from pathlib import Path

import numpy as np


def _json_value(value):
    """Convert NumPy values to strict JSON, preserving non-finite bounds as text."""
    if isinstance(value, np.ndarray):
        return _json_value(value.tolist())
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, float):
        if np.isnan(value):
            return "NaN"
        if np.isposinf(value):
            return "Infinity"
        if np.isneginf(value):
            return "-Infinity"
    return value


@dataclass(eq=False)
class OptimizationResult:
    """Inputs, outputs, and provenance for a single ``fit_theta`` call."""

    run_id: str
    started_at: str
    finished_at: str
    inputs: dict
    outputs: dict
    provenance: dict
    result_path: Path | None = field(default=None, compare=False)
    schema_version: int = 1

    @property
    def x(self):
        return np.asarray(self.outputs["theta"], dtype=float)

    @property
    def fun(self):
        return float(self.outputs["squared_error_years2"])

    @property
    def nit(self):
        return int(self.outputs["iterations"])

    @property
    def nfev(self):
        return int(self.outputs["objective_evaluations"])

    @property
    def history(self):
        return self.outputs["history"]

    @property
    def success(self):
        return bool(self.outputs["success"])

    @property
    def message(self):
        return self.outputs["message"]

    def to_dict(self):
        return _json_value({
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "provenance": self.provenance,
        })

    def save_json(self, path):
        """Write a new result file without replacing an existing run."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as target:
            json.dump(self.to_dict(), target, indent=2, allow_nan=False)
            target.write("\n")
        self.result_path = path.resolve()
        return self.result_path

    @classmethod
    def from_json(cls, path):
        path = Path(path)
        with path.open(encoding="utf-8") as source:
            data = json.load(source)
        if data["schema_version"] != 1:
            raise ValueError(f"Unsupported result schema: {data['schema_version']}")
        return cls(
            run_id=data["run_id"],
            started_at=data["started_at"],
            finished_at=data["finished_at"],
            inputs=data["inputs"],
            outputs=data["outputs"],
            provenance=data["provenance"],
            result_path=path.resolve(),
            schema_version=data["schema_version"],
        )
