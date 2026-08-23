#!/usr/bin/env python3
"""Recompute the two representative-case values reported in the HIL section.

The overtake interval follows the manuscript definition: first logged entry
into OVERTAKE to the first later sample with Delta_s < 0. No interpolation is
used, so every reported value is directly traceable to a recorded sample.
"""

from __future__ import annotations

import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CASES = (
    ("I", "case_02.json", (1.13, -0.48, 73.10, 0.02, 0.26)),
    ("II", "case_05.json", (8.63, -0.84, 65.83, 0.05, 1.82)),
)


def rms(samples: list[dict], key: str) -> float:
    return math.sqrt(sum(float(row[key]) ** 2 for row in samples) / len(samples))


def metrics(path: Path) -> tuple[float, float, float, float, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    samples = payload["samples"]
    overtake = next(row for row in samples if row["mode_name"] == "OVERTAKE")
    crossover = next(
        row
        for row in samples
        if row["t"] >= overtake["t"] and float(row["Delta_s"]) < 0.0
    )
    return (
        float(crossover["t"]) - float(overtake["t"]),
        min(float(row["Delta_s"]) for row in samples),
        max(float(row["ego_V"]) for row in samples),
        rms(samples, "e_l"),
        rms(samples, "e_v"),
    )


def main() -> None:
    print("scenario,interval_s,min_Delta_s_m,max_V_mps,rms_e_l_m,rms_e_v_mps")
    for scenario, filename, expected in CASES:
        observed = metrics(ROOT / filename)
        rounded = tuple(round(value, 2) for value in observed)
        if rounded != expected:
            raise SystemExit(
                f"{scenario}: observed {rounded}, expected manuscript values {expected}"
            )
        print(scenario + "," + ",".join(f"{value:.6f}" for value in observed))


if __name__ == "__main__":
    main()
