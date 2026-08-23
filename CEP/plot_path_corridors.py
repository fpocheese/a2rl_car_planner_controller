#!/usr/bin/env python3
"""Reproduce the three readable path-and-corridor panels from the HIL logs."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent
CASES = {
    "02": (ROOT / "case_02.json", 228.0, 96.0),
    "05": (ROOT / "case_05.json", 228.0, 96.0),
    "04": (ROOT / "case_04_trimmed.json", 228.0, 96.0),
}


def unwrap_from_origin(values: np.ndarray, origin: float,
                       track_length: float) -> np.ndarray:
    """Return continuous signed progress relative to a fixed track origin."""
    phase = 2.0 * np.pi * (np.asarray(values, dtype=float) - origin) / track_length
    return np.unwrap(phase) * track_length / (2.0 * np.pi)


def local_progress(values: np.ndarray, track_length: float) -> np.ndarray:
    """Unwrap one preview polyline relative to its first station."""
    values = np.asarray(values, dtype=float)
    phase = 2.0 * np.pi * (values - values[0]) / track_length
    return np.unwrap(phase) * track_length / (2.0 * np.pi)


def interpolate_monotone(query: float, xp: np.ndarray,
                         fp: np.ndarray) -> float:
    """Linear interpolation with an explicit strictly increasing time guard."""
    if not np.all(np.diff(xp) > 0.0):
        raise ValueError("sample times must be strictly increasing")
    if query <= xp[0]:
        return float(fp[0])
    if query >= xp[-1]:
        return float(fp[-1])
    right = int(np.searchsorted(xp, query, side="right"))
    left = right - 1
    weight = (query - xp[left]) / (xp[right] - xp[left])
    return float((1.0 - weight) * fp[left] + weight * fp[right])


def save_panel(fig: plt.Figure, stem: Path) -> None:
    """Export without tight cropping so the PDF has the declared media box."""
    fig.savefig(stem.with_suffix(".svg"), facecolor="white")
    fig.savefig(stem.with_suffix(".pdf"), facecolor="white")
    fig.savefig(stem.with_suffix(".png"), dpi=600, facecolor="white")
    fig.savefig(stem.with_suffix(".tiff"), dpi=600, facecolor="white")
    plt.close(fig)


def plot_case(case_id: str, source: Path, width_pt: float,
              height_pt: float) -> None:
    with source.open("r", encoding="utf-8") as handle:
        record = json.load(handle)

    samples = record["samples"]
    guidance_events = record["guidance_events"]
    if not samples or not guidance_events:
        raise ValueError(f"case {case_id} has no samples or guidance events")

    time = np.asarray([row["t"] for row in samples], dtype=float)
    ego_s = np.asarray([row["ego_s"] for row in samples], dtype=float)
    ego_n = np.asarray([row["ego_n"] for row in samples], dtype=float)
    opp_s = np.asarray([row["opp_s"] for row in samples], dtype=float)
    opp_n = np.asarray([row["opp_n"] for row in samples], dtype=float)
    track_length = float(samples[0]["L_trk"])
    origin_s = float(ego_s[0])

    ego_progress = unwrap_from_origin(ego_s, origin_s, track_length)
    opp_progress = unwrap_from_origin(opp_s, origin_s, track_length)

    fig, ax = plt.subplots(figsize=(width_pt / 72.0, height_pt / 72.0))
    fig.subplots_adjust(left=0.16, right=0.985, bottom=0.31, top=0.96)

    preview_x_max = float(np.max(ego_progress))
    corridor_min = float(np.min(ego_n))
    corridor_max = float(np.max(ego_n))
    for event in guidance_events:
        stations = np.asarray(event["s"], dtype=float)
        lower = np.asarray(event["Lmin"], dtype=float)
        upper = np.asarray(event["Lmax"], dtype=float)
        if not (len(stations) == len(lower) == len(upper)):
            raise ValueError(f"case {case_id} contains a malformed corridor event")
        event_progress = interpolate_monotone(
            float(event["t"]), time, ego_progress)
        station_progress = event_progress + local_progress(stations, track_length)
        ax.fill_between(station_progress, lower, upper, color="#9ec5fe",
                        alpha=0.075, linewidth=0.0, zorder=1)
        preview_x_max = max(preview_x_max, float(np.max(station_progress)))
        corridor_min = min(corridor_min, float(np.min(lower)))
        corridor_max = max(corridor_max, float(np.max(upper)))

    ax.plot(ego_progress, ego_n, color="#0F4D92", linewidth=2.0,
            label="Ego", zorder=3)
    ax.plot(opp_progress, opp_n, color="#B64342", linewidth=1.7,
            linestyle="--", label="Opponent", zorder=3)
    ax.axhline(0.0, color="0.25", linewidth=0.8, linestyle=":", zorder=2)

    x_margin = max(5.0, 0.015 * preview_x_max)
    ax.set_xlim(-x_margin, preview_x_max + x_margin)
    y_span = max(1.0, corridor_max - corridor_min)
    ax.set_ylim(corridor_min - 0.08 * y_span, corridor_max + 0.08 * y_span)
    ax.set_xlabel("s − s₀ [m]", fontsize=12.0, labelpad=1.8)
    ax.set_ylabel("n [m]", fontsize=12.0, labelpad=1.8)
    ax.tick_params(axis="both", labelsize=10.8, length=3.0, width=0.8,
                   pad=1.8)
    ax.grid(True, color="0.86", linewidth=0.55, alpha=0.8)
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)
    ax.legend(loc="upper right", frameon=False, fontsize=10.8,
              handlelength=1.5, borderaxespad=0.15, labelspacing=0.12,
              ncol=2, columnspacing=0.8)

    save_panel(fig, ROOT / f"case_{case_id}_path_corridor")


def main() -> None:
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "mathtext.fontset": "dejavusans",
        "axes.unicode_minus": True,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    for case_id, (source, width_pt, height_pt) in CASES.items():
        plot_case(case_id, source, width_pt, height_pt)


if __name__ == "__main__":
    main()
