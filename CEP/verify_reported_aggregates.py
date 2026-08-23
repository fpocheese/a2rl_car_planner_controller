#!/usr/bin/env python3
"""Verify manuscript aggregate values, intervals, tests, and LaTeX tables.

This script never creates lap-level observations.  It checks only the
author-attested aggregate record in ``reported_aggregate_results.json``.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Iterable

try:
    from scipy.stats import beta
except ImportError as exc:  # pragma: no cover - explicit dependency error
    raise SystemExit("SciPy is required for the exact Clopper-Pearson interval") from exc


ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT / "reported_aggregate_results.json"
DEFAULT_TEX = ROOT / "comparison_tables.tex"


def clopper_pearson(successes: int, trials: int, alpha: float = 0.05) -> tuple[float, float]:
    lower = 0.0 if successes == 0 else float(beta.ppf(alpha / 2.0, successes, trials - successes + 1))
    upper = 1.0 if successes == trials else float(beta.ppf(1.0 - alpha / 2.0, successes + 1, trials - successes))
    return lower, upper


def two_proportion_z_test(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float]:
    p1 = x1 / n1
    p2 = x2 / n2
    pooled = (x1 + x2) / (n1 + n2)
    standard_error = math.sqrt(pooled * (1.0 - pooled) * (1.0 / n1 + 1.0 / n2))
    z_score = (p1 - p2) / standard_error
    p_value = math.erfc(abs(z_score) / math.sqrt(2.0))
    return z_score, p_value


def holm_adjust(p_values: Iterable[float]) -> list[float]:
    values = list(p_values)
    order = sorted(range(len(values)), key=values.__getitem__)
    adjusted = [0.0] * len(values)
    running = 0.0
    total = len(values)
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (total - rank) * values[index]))
        adjusted[index] = running
    return adjusted


def table_section(tex: str, label: str, next_label: str | None) -> str:
    start = tex.index(f"\\label{{{label}}}")
    end = len(tex) if next_label is None else tex.index(f"\\label{{{next_label}}}", start)
    return tex[start:end]


def numeric_row(section: str, row_prefix: str) -> list[float]:
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if line.startswith(row_prefix):
            cells = line.split("&")[1:]
            return [float(re.search(r"-?\d+(?:\.\d+)?", cell).group(0)) for cell in cells]
    raise AssertionError(f"row not found in LaTeX table: {row_prefix}")


def assert_close_list(actual: Iterable[float], expected: Iterable[float], tolerance: float = 5e-10) -> None:
    actual_values = list(actual)
    expected_values = list(expected)
    if len(actual_values) != len(expected_values):
        raise AssertionError(f"length mismatch: {actual_values} versus {expected_values}")
    for index, (left, right) in enumerate(zip(actual_values, expected_values)):
        if not math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance):
            raise AssertionError(f"value mismatch at position {index}: {left} versus {right}")


def verify_table_alignment(record: dict, tex_path: Path) -> None:
    tex = tex_path.read_text(encoding="utf-8")
    comparison = table_section(tex, "tab:comparison", "tab:ablation")
    ablation = table_section(tex, "tab:ablation", None)
    comparison_rows = record["comparison"]
    ablation_rows = record["ablation"]

    mappings = (
        ("OSR", "osr_percent"),
        ("TTO", "tto_seconds"),
        ("Min. gap", "mean_minimum_gap_metres"),
        ("Coll.", "collisions"),
        ("Mean TTC", "mean_ttc_seconds"),
        ("Track viol.", "track_violation_percent"),
        ("PFR", "path_feasibility_ratio"),
    )
    for prefix, key in mappings:
        assert_close_list(numeric_row(comparison, prefix), [row[key] for row in comparison_rows])
    comparison_full_osr = comparison_rows[0]["osr_percent"]
    assert_close_list(
        numeric_row(comparison, "OSR def."),
        [comparison_full_osr - row["osr_percent"] for row in comparison_rows],
    )

    ablation_mappings = (
        ("OSR", "osr_percent"),
        ("TTO", "tto_seconds"),
        ("Coll.", "collisions"),
        ("Min. gap", "mean_minimum_gap_metres"),
        ("Mean TTC", "mean_ttc_seconds"),
        ("PFR", "path_feasibility_ratio"),
    )
    for prefix, key in ablation_mappings:
        assert_close_list(numeric_row(ablation, prefix), [row[key] for row in ablation_rows])
    ablation_full_osr = ablation_rows[0]["osr_percent"]
    assert_close_list(
        numeric_row(ablation, "OSR loss"),
        [ablation_full_osr - row["osr_percent"] for row in ablation_rows],
    )


def compare_family(full: dict, alternatives: list[dict], name_key: str) -> list[dict]:
    raw = [
        two_proportion_z_test(full["successes"], full["laps"], other["successes"], other["laps"])
        for other in alternatives
    ]
    adjusted = holm_adjust(item[1] for item in raw)
    return [
        {
            "comparison": f"{full[name_key]} vs {other[name_key]}",
            "difference_percentage_points": full["osr_percent"] - other["osr_percent"],
            "z": z_score,
            "raw_p": p_value,
            "holm_p": adjusted[index],
        }
        for index, (other, (z_score, p_value)) in enumerate(zip(alternatives, raw))
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--tex", type=Path, default=DEFAULT_TEX)
    parser.add_argument("--json", action="store_true", help="emit the verification report as JSON")
    args = parser.parse_args()

    record = json.loads(args.data.read_text(encoding="utf-8"))
    for family in (record["comparison"], record["ablation"]):
        for row in family:
            expected_successes = round(row["osr_percent"] * row["laps"] / 100.0)
            if row["successes"] != expected_successes:
                raise AssertionError(f"OSR/count mismatch in {row}")

    headline = record["headline"]
    interval = clopper_pearson(headline["successes"], headline["laps"])
    rounded_interval = [round(100.0 * bound, 1) for bound in interval]
    assert_close_list(rounded_interval, headline["clopper_pearson_95_percent"])
    verify_table_alignment(record, args.tex)

    baseline_tests = compare_family(record["comparison"][0], record["comparison"][1:], "method")
    ablation_tests = compare_family(record["ablation"][0], record["ablation"][1:], "variant")
    if not all(test["holm_p"] < 1e-6 for test in baseline_tests + ablation_tests):
        raise AssertionError("manuscript statement 'Holm-adjusted p < 1e-6' is not satisfied")

    report = {
        "status": "PASS",
        "headline_osr_percent": 100.0 * headline["successes"] / headline["laps"],
        "clopper_pearson_95_percent_unrounded": [100.0 * interval[0], 100.0 * interval[1]],
        "clopper_pearson_95_percent_reported": rounded_interval,
        "baseline_tests": baseline_tests,
        "ablation_tests": ablation_tests,
        "latex_tables_match_json": True,
        "lap_level_data_generated": False,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("PASS: reported aggregate results are internally consistent")
        print(f"  OSR: {report['headline_osr_percent']:.1f}% (947/1000)")
        lo, hi = report["clopper_pearson_95_percent_unrounded"]
        print(f"  exact 95% CI: {lo:.6f}--{hi:.6f}% (reported 93.1--96.0%)")
        print("  LaTeX comparison and ablation tables match the JSON record")
        print("  all eight Holm-adjusted OSR comparisons satisfy p < 1e-6")
        print("  no lap-level observations were generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
