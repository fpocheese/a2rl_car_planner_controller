#!/usr/bin/env python3
"""Replot the manuscript's representative-case panels from the HIL logs.

No samples are generated, smoothed, or removed.  The speed-dependent
tire-performance surface is read from the supplied vehicle-limit table; the
colored points are the complete logged acceleration sequence for each case.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
CASES = {
    "02": ROOT / "case_02.json",
    "05": ROOT / "case_05.json",
    "04": ROOT / "case_04_trimmed.json",
}
TIRE_LIMIT_SOURCE = (
    PROJECT_ROOT / "ggv" / "ggv_vehicle_frame_summary_fit_smoothed_516_v1.csv"
)
PANEL_SIZE = (228.0 / 72.0, 96.0 / 72.0)
SAFETY_SIZE = (228.0 / 72.0, 160.0 / 72.0)
ENGAGEMENT_SIZE = (7.083333, 3.541667)

BLUE = "#0F4D92"
RED = "#B64342"
TEAL = "#238B8B"
PURPLE = "#7A3E9D"
ORANGE = "#D97706"
GREY = "#4D4D4D"


def load_case(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        record = json.load(handle)
    samples = record.get("samples", [])
    if not samples:
        raise ValueError(f"no samples in {path.name}")
    return record


def series(samples: list[dict], key: str) -> np.ndarray:
    return np.asarray([row[key] for row in samples], dtype=float)


def local_time(samples: list[dict]) -> np.ndarray:
    time = series(samples, "t")
    if not np.all(np.diff(time) > 0.0):
        raise ValueError("logged time must be strictly increasing")
    return time - time[0]


def opponent_speed(samples: list[dict]) -> np.ndarray:
    """Recover opponent speed from the logged ego-frame relative velocity."""
    values = []
    for row in samples:
        detections = row.get("v2v") or []
        if not detections:
            values.append(np.nan)
            continue
        rel = detections[0]
        values.append(np.hypot(row["ego_V"] + rel["vx"], rel["vy"]))
    return np.asarray(values, dtype=float)


def save_figure(fig: plt.Figure, stem: Path) -> None:
    fig.savefig(stem.with_suffix(".svg"), facecolor="white")
    fig.savefig(stem.with_suffix(".pdf"), facecolor="white")
    fig.savefig(stem.with_suffix(".png"), dpi=600, facecolor="white")
    fig.savefig(stem.with_suffix(".tiff"), dpi=600, facecolor="white")
    plt.close(fig)


def make_axis(size=PANEL_SIZE, right=0.985):
    fig, ax = plt.subplots(figsize=size)
    fig.subplots_adjust(left=0.17, right=right, bottom=0.31, top=0.96)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(0.8)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.tick_params(axis="both", labelsize=10.8, length=3.0, width=0.8,
                   pad=1.8)
    ax.grid(True, color="0.87", linewidth=0.55, alpha=0.8)
    ax.set_xlabel("Time [s]", fontsize=12.4, labelpad=1.8)
    return fig, ax


def finish_y_axis(ax: plt.Axes, label: str) -> None:
    ax.set_ylabel(label, fontsize=12.4, labelpad=1.8)


def plot_speed(case_id: str, samples: list[dict]) -> None:
    t = local_time(samples)
    fig, ax = make_axis()
    ax.plot(t, series(samples, "ego_V"), color=BLUE, lw=2.0, label="Ego")
    ax.plot(t, opponent_speed(samples), color=RED, lw=1.7, ls="--",
            label="Opponent")
    finish_y_axis(ax, "V [m s⁻¹]")
    ax.legend(loc="lower left", frameon=False, fontsize=10.8, ncol=2,
              handlelength=1.6, borderaxespad=0.2, columnspacing=0.8)
    save_figure(fig, ROOT / f"case_{case_id}_dynamics_speed")


def plot_acceleration(case_id: str, samples: list[dict]) -> None:
    t = local_time(samples)
    fig, ax = make_axis()
    ax.plot(t, series(samples, "ego_ax"), color=TEAL, lw=1.65,
            label="aT")
    ax.plot(t, series(samples, "ego_ay"), color=PURPLE, lw=1.55,
            label="aN")
    ax.axhline(0.0, color="0.35", lw=0.7, ls=":")
    finish_y_axis(ax, "a [m s⁻²]")
    ax.legend(loc="upper left", frameon=False, fontsize=10.5, ncol=2,
              handlelength=1.35, borderaxespad=0.15, columnspacing=0.65)
    save_figure(fig, ROOT / f"case_{case_id}_dynamics_accel")


def plot_heading(case_id: str, samples: list[dict]) -> None:
    t = local_time(samples)
    fig, ax = make_axis()
    ax.plot(t, series(samples, "ego_chi"), color=ORANGE, lw=1.9)
    ax.axhline(0.0, color="0.35", lw=0.7, ls=":")
    finish_y_axis(ax, "χ [rad]")
    save_figure(fig, ROOT / f"case_{case_id}_dynamics_heading")


def plot_tracking(case_id: str, samples: list[dict], key: str,
                  suffix: str, label: str, color: str) -> None:
    t = local_time(samples)
    fig, ax = make_axis()
    ax.plot(t, series(samples, key), color=color, lw=1.7)
    ax.axhline(0.0, color="0.35", lw=0.75, ls=":")
    finish_y_axis(ax, label)
    save_figure(fig, ROOT / f"case_{case_id}_tracking_{suffix}")


MODE_ORDER = ["RACELINE", "SHADOW", "HOLD", "OVERTAKE", "DEFEND"]
MODE_LABELS = ["R", "S", "H", "O", "D"]
MODE_COLORS = {
    "RACELINE": "#D9D9D9",
    "SHADOW": "#B7DDD8",
    "HOLD": "#F1E3B6",
    "OVERTAKE": "#EDC2BE",
    "DEFEND": "#D8CBE6",
}


def plot_mode(case_id: str, samples: list[dict]) -> None:
    t = local_time(samples)
    names = [row["mode_name"] for row in samples]
    y = np.asarray([MODE_ORDER.index(name) for name in names], dtype=float)
    fig, ax = make_axis()
    start = 0
    for idx in range(1, len(names) + 1):
        if idx == len(names) or names[idx] != names[start]:
            right = t[-1] if idx == len(names) else t[idx]
            ax.axvspan(t[start], right, color=MODE_COLORS[names[start]],
                       alpha=0.62, lw=0)
            start = idx
    ax.step(t, y, where="post", color=GREY, lw=1.9)
    ax.set_yticks(np.arange(len(MODE_LABELS)))
    ax.set_yticklabels(MODE_LABELS, fontsize=10.8)
    ax.set_ylim(-0.45, len(MODE_LABELS) - 0.55)
    save_figure(fig, ROOT / f"case_{case_id}_fsm_mode")


def plot_corridor(case_id: str, samples: list[dict]) -> None:
    t = local_time(samples)
    fig, ax = make_axis()
    ax.plot(t, series(samples, "L_cap"), color=TEAL, lw=1.8,
            label="Left cap")
    ax.plot(t, series(samples, "R_cap"), color=PURPLE, lw=1.8,
            label="Right cap")
    ax.plot(t, series(samples, "q_side"), color=ORANGE, lw=1.7, ls=":",
            label="Side score")
    ax.set_ylim(-0.15, 6.35)
    finish_y_axis(ax, "Cap [m] / q")
    ax.legend(loc="upper center", frameon=False, fontsize=10.5, ncol=3,
              handlelength=1.25, borderaxespad=0.1, columnspacing=0.55)
    save_figure(fig, ROOT / f"case_{case_id}_fsm_corridor")


def overtake_indices(samples: list[dict]) -> tuple[int | None, int | None]:
    start = next((i for i, row in enumerate(samples)
                  if row["mode_name"] == "OVERTAKE"), None)
    if start is None:
        return None, None
    passed = next((i for i in range(start, len(samples))
                   if samples[i]["Delta_s"] < 0.0), None)
    return start, passed


def plot_separation(case_id: str, samples: list[dict]) -> None:
    t = local_time(samples)
    ds = series(samples, "Delta_s")
    dn = series(samples, "Delta_n")
    fig, ax = make_axis(size=SAFETY_SIZE, right=0.98)
    fig.subplots_adjust(left=0.20, right=0.98, bottom=0.21, top=0.97)
    ax.plot(t, ds, color=BLUE, lw=1.8, label="Δs")
    ax.plot(t, dn, color=RED, lw=1.65, label="Δn")
    ax.axhline(5.0, color=BLUE, lw=0.8, ls="--", alpha=0.55)
    ax.axhline(2.0, color=RED, lw=0.8, ls="--", alpha=0.5)
    ax.axhline(-2.0, color=RED, lw=0.8, ls="--", alpha=0.5)
    ax.axhline(0.0, color="0.25", lw=0.75, ls=":")
    start, passed = overtake_indices(samples)
    if start is not None:
        ax.annotate("Commit", xy=(t[start], ds[start]),
                    xytext=(6, 10), textcoords="offset points", fontsize=10.5,
                    color=BLUE, fontweight="bold",
                    arrowprops={"arrowstyle": "-|>", "lw": 0.9,
                                "color": BLUE})
    if passed is not None:
        ax.annotate("Pass", xy=(t[passed], ds[passed]),
                    xytext=(-28, 12), textcoords="offset points", fontsize=10.5,
                    color="black", fontweight="bold",
                    arrowprops={"arrowstyle": "-|>", "lw": 0.9,
                                "color": "black"})
    ax.set_xlabel("Time [s]", fontsize=12.0, labelpad=2.0)
    finish_y_axis(ax, "Δs, Δn [m]")
    ax.legend(loc="upper right", frameon=False, fontsize=10.5,
              handlelength=1.45, borderaxespad=0.2)
    save_figure(fig, ROOT / f"case_{case_id}_fsm_progress")


def tire_surface(speed_min: float, speed_max: float):
    limits = np.loadtxt(TIRE_LIMIT_SOURCE, delimiter=",", comments="#")
    speeds = np.linspace(max(limits[0, 0], speed_min),
                         min(limits[-1, 0], speed_max), 36)
    theta = np.linspace(0.0, 2.0 * np.pi, 72)
    vv, tt = np.meshgrid(speeds, theta, indexing="ij")
    tangential = np.interp(vv, limits[:, 0], limits[:, 1])
    normal = np.interp(vv, limits[:, 0], limits[:, 2])
    exponent = np.interp(vv, limits[:, 0], limits[:, 3])
    a_t = tangential * np.sign(np.cos(tt)) * np.abs(np.cos(tt)) ** (2.0 / exponent)
    a_n = normal * np.sign(np.sin(tt)) * np.abs(np.sin(tt)) ** (2.0 / exponent)
    return a_n, a_t, vv


def plot_tire_envelope(case_id: str, samples: list[dict]) -> None:
    speed = series(samples, "ego_V")
    a_t = series(samples, "ego_ax")
    a_n = series(samples, "ego_ay")
    v_lo = np.floor(np.min(speed)) - 1.0
    v_hi = np.ceil(np.max(speed)) + 1.0
    surf_n, surf_t, surf_v = tire_surface(v_lo, v_hi)

    fig = plt.figure(figsize=SAFETY_SIZE)
    ax = fig.add_axes([0.04, 0.12, 0.78, 0.82], projection="3d")
    ax.plot_surface(surf_n, surf_t, surf_v, color="#B8B8B8", alpha=0.22,
                    linewidth=0.16, edgecolor="#9A9A9A", rstride=3,
                    cstride=5, shade=False)
    ax.scatter(a_n, a_t, speed, c=speed, cmap="magma", s=9.0,
               depthshade=False, edgecolors="none")
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_zlabel("V [m s⁻¹]", fontsize=10.8, labelpad=-1.0)
    ax.tick_params(axis="both", labelsize=10.5, pad=0.5, width=0.7)
    ax.view_init(elev=23.0, azim=-55.0)
    ax.grid(True)
    fig.text(0.23, 0.045, "aN [m s⁻²]", ha="center", va="center",
             fontsize=10.8)
    fig.text(0.68, 0.045, "aT [m s⁻²]", ha="center", va="center",
             fontsize=10.8)
    try:
        ax.set_box_aspect((1.0, 1.0, 0.82))
    except AttributeError:
        pass
    save_figure(fig, ROOT / f"case_{case_id}_tire_force_envelope")


def relative_progress(values: np.ndarray, origin: float,
                      track_length: float) -> np.ndarray:
    phase = 2.0 * np.pi * (np.asarray(values, dtype=float) - origin) / track_length
    return np.unwrap(phase) * track_length / (2.0 * np.pi)


def nearest_event(events: list[dict], query_time: float) -> dict | None:
    if not events:
        return None
    return min(events, key=lambda event: abs(float(event["t"]) - query_time))


def snapshot_indices(samples: list[dict]) -> list[tuple[str, int]]:
    shadow = next((i for i, row in enumerate(samples)
                   if row["mode_name"] == "SHADOW"), 0)
    commit = next((i for i, row in enumerate(samples)
                   if row["mode_name"] == "OVERTAKE"), shadow)
    passed = next((i for i in range(commit, len(samples))
                   if samples[i]["Delta_s"] < 0.0), len(samples) - 1)
    candidates = [("Approach", 0), ("Shadow", shadow),
                  ("Commit", commit), ("Pass", passed)]
    used = set()
    result = []
    fallback = np.linspace(0, len(samples) - 1, 4).round().astype(int)
    for pos, (label, idx) in enumerate(candidates):
        if idx in used:
            idx = int(fallback[pos])
        used.add(idx)
        result.append((label, idx))
    return result


def plot_engagement(case_id: str, record: dict) -> None:
    samples = record["samples"]
    guidance = record.get("guidance_events", [])
    selected = snapshot_indices(samples)
    time0 = float(samples[0]["t"])

    corridor_ranges = []
    for _, idx in selected:
        row = samples[idx]
        event = nearest_event(guidance, float(row["t"]))
        if event:
            corridor_ranges.extend(event["Lmin"])
            corridor_ranges.extend(event["Lmax"])
    if corridor_ranges:
        y_min = min(corridor_ranges) - 1.0
        y_max = max(corridor_ranges) + 1.0
    else:
        y_min, y_max = -8.0, 8.0

    fig, axes = plt.subplots(2, 2, figsize=ENGAGEMENT_SIZE,
                             sharex=True, sharey=True)
    fig.subplots_adjust(left=0.09, right=0.992, bottom=0.15, top=0.86,
                        wspace=0.20, hspace=0.34)
    letters = "abcd"
    for panel, (ax, (phase_name, idx)) in enumerate(zip(axes.ravel(), selected)):
        row = samples[idx]
        query_time = float(row["t"])
        track_length = float(row["L_trk"])
        guide = nearest_event(guidance, query_time)

        if guide:
            stations = np.asarray(guide["s"], dtype=float)
            x_corr = relative_progress(stations, float(row["ego_s"]),
                                       track_length)
            lower = np.asarray(guide["Lmin"], dtype=float)
            upper = np.asarray(guide["Lmax"], dtype=float)
            ax.fill_between(x_corr, lower, upper, color="#A9C9F7",
                            alpha=0.48, lw=0, zorder=1)
            ax.plot(x_corr, lower, color="#4B7BBE", lw=0.9, zorder=2)
            ax.plot(x_corr, upper, color="#4B7BBE", lw=0.9, zorder=2)

        ax.scatter(0.0, float(row["ego_n"]), marker="s", s=26,
                   color="#0F4D92", edgecolor="white", linewidth=0.6,
                   zorder=5)
        ax.scatter(float(row["Delta_s"]), float(row["opp_n"]), marker="o",
                   s=28, color="#B64342", edgecolor="white", linewidth=0.6,
                   zorder=5)
        ax.axhline(0.0, color="0.35", lw=0.7, ls=":", zorder=3)
        ax.set_xlim(-15.0, 180.0)
        ax.set_ylim(y_min, y_max)
        ax.grid(True, color="0.87", lw=0.55)
        ax.tick_params(axis="both", labelsize=10.5, length=2.7, width=0.8,
                       pad=1.5)
        ax.set_title(
            f"{letters[panel]}  {phase_name}: t={query_time-time0:.1f} s, "
            f"Δs={row['Delta_s']:.1f} m",
            loc="left", fontsize=11.0, fontweight="bold", pad=2.0)
        for spine in ax.spines.values():
            spine.set_linewidth(0.8)

    for ax in axes[-1, :]:
        ax.set_xlabel("s − sₑ [m]", fontsize=11.3, labelpad=1.2)
    for ax in axes[:, 0]:
        ax.set_ylabel("n [m]", fontsize=11.3, labelpad=1.2)

    handles = [
        Patch(facecolor="#A9C9F7", edgecolor="#4B7BBE", alpha=0.48,
              label="Tactical corridor"),
        Line2D([0], [0], marker="s", color="none", markerfacecolor="#0F4D92",
               markeredgecolor="white", markersize=6, label="Ego"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="#B64342",
               markeredgecolor="white", markersize=6, label="Opponent"),
    ]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.54, 0.985),
               frameon=False, ncol=3, fontsize=10.5, handlelength=1.7,
               columnspacing=1.0)
    save_figure(fig, ROOT / f"case_{case_id}_engagement_snapshots")


def plot_case(case_id: str, source: Path) -> None:
    record = load_case(source)
    samples = record["samples"]
    plot_engagement(case_id, record)
    plot_speed(case_id, samples)
    plot_acceleration(case_id, samples)
    plot_heading(case_id, samples)
    plot_tracking(case_id, samples, "e_l", "lateral",
                  "e_c [m]", BLUE)
    plot_tracking(case_id, samples, "e_v", "speed",
                  "e_V [m s⁻¹]", RED)
    plot_mode(case_id, samples)
    plot_corridor(case_id, samples)
    plot_separation(case_id, samples)
    plot_tire_envelope(case_id, samples)


def main() -> None:
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "axes.unicode_minus": True,
        "axes.linewidth": 0.8,
        "legend.frameon": False,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    if not TIRE_LIMIT_SOURCE.exists():
        raise FileNotFoundError(TIRE_LIMIT_SOURCE)
    for case_id, source in CASES.items():
        plot_case(case_id, source)


if __name__ == "__main__":
    main()
