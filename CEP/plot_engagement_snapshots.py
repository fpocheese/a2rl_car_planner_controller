#!/usr/bin/env python3
"""Rebuild the three engagement-geometry figures from the recorded logs.

The plot keeps the original Cartesian geometry: physical track edges, the
game-layer feasible corridor, every point of the desired planner horizon, and
oriented vehicle glyphs.  No observations are generated or smoothed.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


ROOT = Path(__file__).resolve().parent
RACECAR_ROOT = Path(__file__).resolve().parents[2]
CASES = {
    "02": ROOT / "case_02.json",
    "05": ROOT / "case_05.json",
    "04": ROOT / "case_04_trimmed.json",
}
TRACK_CANDIDATES = (
    RACECAR_ROOT
    / "src/planner_cvxopt/config/tracks/North_Line/"
    "RaceLine_11_15_0610115_1725_fix19_exp10.csv",
    RACECAR_ROOT
    / "install/planner_cvxopt/share/planner_cvxopt/config/tracks/North_Line/"
    "RaceLine_11_15_0610115_1725_fix19_exp10.csv",
    RACECAR_ROOT
    / "src/planner_cvxopt/config/tracks/North_Line/BaseLine.csv",
)

FIGURE_WIDTH_MM = 89.0
FIGURE_HEIGHT_MM = 154.0
FIGURE_SIZE = (FIGURE_WIDTH_MM / 25.4, FIGURE_HEIGHT_MM / 25.4)

TRACK = "#252525"
CORRIDOR_EDGE = "#3676C4"
CORRIDOR_FILL = "#A9C9F7"
PLAN = "#178A68"
EGO = "#175A9C"
OPPONENT = "#C14943"

DELTA_TOP_LEFT = {
    "05": {0, 1, 2},  # Fig. 9(a--c)
    "04": {0, 1, 2},  # Fig. 13(a--c)
}


class TrackGeometry:
    """Periodic Frenet-to-Cartesian map from the recorded North Line track."""

    def __init__(
        self,
        s: np.ndarray,
        x: np.ndarray,
        y: np.ndarray,
        heading: np.ndarray,
        left: np.ndarray,
        right: np.ndarray,
    ) -> None:
        self.s = s
        self.x = x
        self.y = y
        self.heading = heading
        self.left = left
        self.right = np.where(right > 0.0, -np.abs(right), right)
        self.length = float(s[-1])

    def _interp(self, query: np.ndarray, values: np.ndarray) -> np.ndarray:
        return np.interp(
            np.mod(np.asarray(query, dtype=float), self.length),
            self.s,
            values,
            period=self.length,
        )

    def heading_at(self, query: np.ndarray) -> np.ndarray:
        sin_h = self._interp(query, np.sin(self.heading))
        cos_h = self._interp(query, np.cos(self.heading))
        return np.arctan2(sin_h, cos_h)

    def frenet_to_xy(
        self, query: np.ndarray, lateral: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        query = np.asarray(query, dtype=float)
        lateral = np.asarray(lateral, dtype=float)
        x_ref = self._interp(query, self.x)
        y_ref = self._interp(query, self.y)
        heading = self.heading_at(query)
        return (
            x_ref - lateral * np.sin(heading),
            y_ref + lateral * np.cos(heading),
        )

    def boundaries(
        self, query: np.ndarray
    ) -> tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]:
        left = self._interp(query, self.left)
        right = self._interp(query, self.right)
        return self.frenet_to_xy(query, left), self.frenet_to_xy(query, right)


def load_track() -> TrackGeometry:
    required = {"Sref", "Xref", "Yref", "Aref", "Lmax", "Lmin"}
    for source in TRACK_CANDIDATES:
        if not source.exists():
            continue
        columns: dict[str, list[float]] = {key: [] for key in required}
        with source.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not required.issubset(reader.fieldnames or []):
                continue
            for row in reader:
                for key in required:
                    columns[key].append(float(row[key]))
        if len(columns["Sref"]) > 10:
            return TrackGeometry(
                np.asarray(columns["Sref"]),
                np.asarray(columns["Xref"]),
                np.asarray(columns["Yref"]),
                np.asarray(columns["Aref"]),
                np.asarray(columns["Lmax"]),
                np.asarray(columns["Lmin"]),
            )
    raise FileNotFoundError("North Line track geometry CSV was not found")


def load_case(source: Path) -> dict[str, Any]:
    with source.open("r", encoding="utf-8") as handle:
        record = json.load(handle)
    if not record.get("samples"):
        raise ValueError(f"no recorded samples in {source.name}")
    return record


def values(samples: list[dict[str, Any]], key: str) -> np.ndarray:
    return np.asarray([row.get(key, math.nan) for row in samples], dtype=float)


def nearest(rows: list[dict[str, Any]], query_time: float) -> dict[str, Any]:
    if not rows:
        return {}
    return min(rows, key=lambda row: abs(float(row.get("t", 0.0)) - query_time))


def unwrap_relative_s(
    station: np.ndarray, reference: float, track_length: float
) -> np.ndarray:
    station = np.asarray(station, dtype=float)
    return reference + (
        (station - reference + 0.5 * track_length) % track_length
        - 0.5 * track_length
    )


def choose_snapshot_times(
    samples: list[dict[str, Any]],
) -> list[tuple[str, float]]:
    """Use the original approach/shadow/overtake/pass event definition."""
    time = values(samples, "t")
    delta_s = values(samples, "Delta_s")

    def first_mode(mode: int, fallback: float) -> float:
        return next(
            (
                float(row["t"])
                for row in samples
                if int(row.get("mode", -1)) == mode
            ),
            fallback,
        )

    start = float(time[0])
    shadow = first_mode(2, start)
    overtake = first_mode(3, shadow)
    pass_indices = np.flatnonzero(delta_s < 0.0)
    passed = float(time[pass_indices[0]]) if pass_indices.size else float(time[-1])
    approach = max(start, min(shadow, overtake) - 2.0)
    return [
        ("Approach", approach),
        ("Shadow", shadow),
        ("Overtake", overtake),
        ("Pass", passed),
    ]


def planner_horizon(
    event: dict[str, Any], max_points: int = 30
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    path = list(event.get("path", []))[:max_points]
    if not path:
        empty = np.asarray([], dtype=float)
        return empty, empty, empty
    x = np.asarray([point.get("x", math.nan) for point in path], dtype=float)
    y = np.asarray([point.get("y", math.nan) for point in path], dtype=float)
    yaw = np.asarray([point.get("psi", math.nan) for point in path], dtype=float)
    valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(yaw)
    return x[valid], y[valid], yaw[valid]


def to_local_xy(
    x: np.ndarray,
    y: np.ndarray,
    origin_x: float,
    origin_y: float,
    heading: float,
) -> tuple[np.ndarray, np.ndarray]:
    dx = np.asarray(x, dtype=float) - origin_x
    dy = np.asarray(y, dtype=float) - origin_y
    cosine = math.cos(heading)
    sine = math.sin(heading)
    return cosine * dx + sine * dy, -sine * dx + cosine * dy


def fill_xy_band(
    axis: plt.Axes,
    left_xy: tuple[np.ndarray, np.ndarray],
    right_xy: tuple[np.ndarray, np.ndarray],
    color: str,
    alpha: float,
    zorder: float,
) -> None:
    left_x, left_y = left_xy
    right_x, right_y = right_xy
    axis.fill(
        np.concatenate((left_x, right_x[::-1])),
        np.concatenate((left_y, right_y[::-1])),
        facecolor=color,
        edgecolor="none",
        alpha=alpha,
        zorder=zorder,
    )


def draw_vehicle(
    axis: plt.Axes,
    x: float,
    y: float,
    heading: float,
    color: str,
) -> None:
    """Draw a compact vehicle point with a short heading arrow.

    The circle and arrow use a fixed display size, so their visual footprint
    remains small even when event-specific Cartesian limits change.  The
    arrow direction is obtained from the data transform and therefore follows
    the vehicle heading in the displayed track geometry.
    """
    axis.scatter(
        [x],
        [y],
        s=19.0,
        marker="o",
        facecolor=color,
        edgecolor="black",
        linewidth=0.45,
        zorder=10,
    )

    start_display = axis.transData.transform((x, y))
    heading_display = axis.transData.transform(
        (x + math.cos(heading), y + math.sin(heading))
    )
    direction = heading_display - start_display
    norm = float(np.hypot(direction[0], direction[1]))
    if norm <= 0.0:
        return
    arrow_length_px = 10.5 * axis.figure.dpi / 72.0
    end_display = start_display + arrow_length_px * direction / norm
    end_data = axis.transData.inverted().transform(end_display)
    axis.annotate(
        "",
        xy=(float(end_data[0]), float(end_data[1])),
        xytext=(x, y),
        arrowprops={
            "arrowstyle": "-|>",
            "color": color,
            "linewidth": 0.9,
            "mutation_scale": 6.5,
            "shrinkA": 2.2,
            "shrinkB": 0.0,
        },
        zorder=11,
    )


def draw_plan(axis: plt.Axes, x: np.ndarray, y: np.ndarray) -> None:
    """Draw the desired path as a single continuous green line."""
    axis.plot(
        x,
        y,
        color=PLAN,
        linewidth=1.5,
        zorder=6,
    )


def finite_extent(arrays: list[np.ndarray]) -> tuple[float, float]:
    finite = np.concatenate(
        [array[np.isfinite(array)] for array in arrays if array.size]
    )
    return float(np.min(finite)), float(np.max(finite))


def plot_case(case_id: str, record: dict[str, Any], track: TrackGeometry) -> None:
    samples = record["samples"]
    lap_length = float(samples[0].get("L_trk", track.length))
    selected = choose_snapshot_times(samples)
    time_origin = float(samples[0]["t"])

    fig, axes = plt.subplots(4, 1, figsize=FIGURE_SIZE)
    fig.subplots_adjust(
        left=0.145,
        right=0.98,
        bottom=0.065,
        top=0.925,
        hspace=0.58,
    )

    for panel_index, (axis, (phase, phase_time)) in enumerate(
        zip(axes.ravel(), selected)
    ):
        trajectory = nearest(record.get("trajectory_events", []), phase_time)
        reference_time = float(trajectory.get("t", phase_time))
        sample = nearest(samples, reference_time)
        ego_s = float(sample["ego_s"])
        opp_s = float(sample["opp_s"])
        opp_n = float(sample["opp_n"])
        opp_s_unwrapped = float(
            unwrap_relative_s(np.asarray([opp_s]), ego_s, lap_length)[0]
        )
        plan_x, plan_y, _plan_yaw = planner_horizon(trajectory)
        if plan_x.size != 30:
            raise ValueError(
                f"case {case_id} at t={reference_time:.3f}: "
                f"expected 30 planned points, found {plan_x.size}"
            )

        origin_x = float(trajectory["origin_x"])
        origin_y = float(trajectory["origin_y"])
        local_heading = float(trajectory["origin_yaw"])
        opponent_heading = float(
            track.heading_at(np.asarray([opp_s_unwrapped]))[0]
            + float(sample.get("opp_chi", 0.0))
        )
        opponent_x, opponent_y = track.frenet_to_xy(
            np.asarray([opp_s_unwrapped]), np.asarray([opp_n])
        )
        opponent_x, opponent_y = to_local_xy(
            opponent_x, opponent_y, origin_x, origin_y, local_heading
        )

        plan_arclength = float(
            np.hypot(plan_x[0], plan_y[0])
            + np.sum(np.hypot(np.diff(plan_x), np.diff(plan_y)))
        )
        forward_station = max(
            120.0,
            plan_arclength + 14.0,
            opp_s_unwrapped - ego_s + 28.0,
        )
        station = np.linspace(ego_s - 28.0, ego_s + forward_station, 720)
        center_x, center_y = track.frenet_to_xy(
            station, np.zeros_like(station)
        )
        (left_x, left_y), (right_x, right_y) = track.boundaries(station)
        center_x, center_y = to_local_xy(
            center_x, center_y, origin_x, origin_y, local_heading
        )
        left_x, left_y = to_local_xy(
            left_x, left_y, origin_x, origin_y, local_heading
        )
        right_x, right_y = to_local_xy(
            right_x, right_y, origin_x, origin_y, local_heading
        )
        fill_xy_band(
            axis,
            (left_x, left_y),
            (right_x, right_y),
            color="#F2F2F2",
            alpha=1.0,
            zorder=0,
        )
        axis.plot(left_x, left_y, color=TRACK, linewidth=0.85, zorder=3)
        axis.plot(right_x, right_y, color=TRACK, linewidth=0.85, zorder=3)
        axis.plot(
            center_x,
            center_y,
            color="#777777",
            linewidth=0.48,
            linestyle=(0, (1.5, 2.0)),
            zorder=2,
        )

        x_sources = [left_x, right_x, center_x, plan_x, opponent_x]
        y_sources = [left_y, right_y, center_y, plan_y, opponent_y]
        guidance = nearest(record.get("guidance_events", []), phase_time)
        if guidance:
            corridor_s = unwrap_relative_s(
                np.asarray(guidance["s"], dtype=float), ego_s, lap_length
            )
            lower = np.asarray(guidance["Lmin"], dtype=float)
            upper = np.asarray(guidance["Lmax"], dtype=float)
            valid = (corridor_s >= station[0]) & (corridor_s <= station[-1])
            upper_x, upper_y = track.frenet_to_xy(
                corridor_s[valid], upper[valid]
            )
            lower_x, lower_y = track.frenet_to_xy(
                corridor_s[valid], lower[valid]
            )
            upper_x, upper_y = to_local_xy(
                upper_x, upper_y, origin_x, origin_y, local_heading
            )
            lower_x, lower_y = to_local_xy(
                lower_x, lower_y, origin_x, origin_y, local_heading
            )
            fill_xy_band(
                axis,
                (upper_x, upper_y),
                (lower_x, lower_y),
                color=CORRIDOR_FILL,
                alpha=0.50,
                zorder=1,
            )
            axis.plot(
                upper_x, upper_y, color=CORRIDOR_EDGE, linewidth=0.68, zorder=4
            )
            axis.plot(
                lower_x, lower_y, color=CORRIDOR_EDGE, linewidth=0.68, zorder=4
            )
            x_sources.extend((upper_x, lower_x))
            y_sources.extend((upper_y, lower_y))

        draw_plan(axis, plan_x, plan_y)
        x_sources.extend((np.asarray([0.0]),))
        y_sources.extend((np.asarray([0.0]),))

        x_min, x_max = finite_extent(x_sources)
        y_min, y_max = finite_extent(y_sources)
        x_margin = max(7.0, 0.025 * (x_max - x_min))
        y_margin = max(5.0, 0.08 * (y_max - y_min))
        axis.set_xlim(x_min - x_margin, x_max + x_margin)
        axis.set_ylim(y_min - y_margin, y_max + y_margin)
        # Keep each event-specific window legible in the one-column 4 x 1
        # manuscript layout.  The numeric axes retain the physical scale;
        # forcing equal screen units would bury straight-track corridors in
        # large empty vertical margins.
        axis.set_aspect("auto")
        draw_vehicle(axis, 0.0, 0.0, 0.0, EGO)
        draw_vehicle(
            axis,
            float(opponent_x[0]),
            float(opponent_y[0]),
            opponent_heading - local_heading,
            OPPONENT,
        )
        axis.grid(True, color="#D9D9D9", linewidth=0.38, zorder=-1)
        axis.tick_params(
            axis="both", labelsize=7.2, length=2.0, width=0.65, pad=1.0
        )
        for spine in axis.spines.values():
            spine.set_linewidth(0.65)

        elapsed = float(sample["t"]) - time_origin
        axis.set_title(
            rf"({chr(97 + panel_index)}) {phase}, "
            rf"$t={elapsed:.1f}\,\mathrm{{s}}$",
            loc="left",
            fontsize=7.4,
            fontweight="normal",
            pad=2.0,
        )
        delta_top = panel_index in DELTA_TOP_LEFT.get(case_id, set())
        axis.text(
            0.02,
            0.95 if delta_top else 0.05,
            rf"$\Delta s={float(sample['Delta_s']):.1f}\,\mathrm{{m}}$",
            transform=axis.transAxes,
            fontsize=7.2,
            ha="left",
            va="top" if delta_top else "bottom",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72,
                  "pad": 1.2},
            zorder=10,
        )

    for axis in axes:
        axis.set_xlabel(r"$x\;[\mathrm{m}]$", fontsize=7.4)
        axis.set_ylabel(r"$y\;[\mathrm{m}]$", fontsize=7.4)

    legend_handles = [
        Line2D([0], [0], color=TRACK, linewidth=0.9, label="Track"),
        Patch(
            facecolor=CORRIDOR_FILL,
            edgecolor=CORRIDOR_EDGE,
            alpha=0.50,
            label=r"$\mathcal{C}_t$",
        ),
        Line2D(
            [0],
            [0],
            color=PLAN,
            linewidth=1.5,
            label="Desired path",
        ),
        Line2D(
            [0], [0], marker="o", color="none", linestyle="none",
            markerfacecolor=EGO, markeredgecolor="black", markersize=4.3,
            label="Ego"
        ),
        Line2D(
            [0], [0], marker="o", color="none", linestyle="none",
            markerfacecolor=OPPONENT, markeredgecolor="black", markersize=4.3,
            label="Opponent"
        ),
    ]
    fig.legend(
        handles=legend_handles,
        loc="upper center",
        bbox_to_anchor=(0.50, 0.985),
        ncol=5,
        frameon=False,
        fontsize=7.2,
        handlelength=1.45,
        columnspacing=0.65,
    )

    stem = ROOT / f"case_{case_id}_engagement_snapshots"
    fig.savefig(stem.with_suffix(".pdf"), facecolor="white")
    fig.savefig(stem.with_suffix(".svg"), facecolor="white")
    fig.savefig(stem.with_suffix(".png"), dpi=600, facecolor="white")
    fig.savefig(stem.with_suffix(".tiff"), dpi=600, facecolor="white")
    plt.close(fig)


def main() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": [
                "Times New Roman", "Times", "Arial", "Helvetica",
                "DejaVu Serif",
            ],
            "mathtext.fontset": "stix",
            "axes.unicode_minus": True,
            "axes.linewidth": 0.85,
            "legend.frameon": False,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    track = load_track()
    for case_id, source in CASES.items():
        plot_case(case_id, load_case(source), track)


if __name__ == "__main__":
    main()
