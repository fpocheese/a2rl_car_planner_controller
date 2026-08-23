#!/usr/bin/env python3
"""Create the compact baseline/ablation OSR summary from reported aggregates."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import beta


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "reported_aggregate_results.json"
OUT = ROOT / "compact_osr_summary"
BLUE = "#0F4D92"
RED = "#B64342"
GREY = "#767676"


def exact_interval(successes: int, laps: int, alpha: float = 0.05):
    lower = 0.0 if successes == 0 else beta.ppf(alpha / 2, successes,
                                                laps - successes + 1)
    upper = 1.0 if successes == laps else beta.ppf(1 - alpha / 2,
                                                   successes + 1,
                                                   laps - successes)
    return 100.0 * lower, 100.0 * upper


def display_name(name: str) -> str:
    names = {
        "Proposed": "Proposed",
        "Non-Interactive MPC": "Non-interactive\nMPC",
        "Without game guidance": "Without game guidance",
        "Without FSM": "Without FSM",
    }
    return names.get(name, name)


def interval_panel(ax, records, key, title, xlim, tick_values,
                   annotate_drops=False):
    labels = [display_name(row[key]) for row in records]
    rates = np.asarray([row["osr_percent"] for row in records], dtype=float)
    intervals = np.asarray([exact_interval(int(row["successes"]),
                                          int(row["laps"]))
                            for row in records])
    y = np.arange(len(records))
    full_rate = rates[0]

    for idx, (rate, interval) in enumerate(zip(rates, intervals)):
        is_full = idx == 0
        color = BLUE if is_full else (RED if annotate_drops else GREY)
        ax.plot(interval, [idx, idx], color=color, lw=2.0 if is_full else 1.4,
                solid_capstyle="round", zorder=2)
        ax.scatter(rate, idx, s=37 if is_full else 27, color=color,
                   edgecolor="white", linewidth=0.6, zorder=3)
        if annotate_drops and not is_full:
            label = f"{rate:.1f} (−{full_rate - rate:.1f} pp)"
        else:
            label = f"{rate:.1f}"
        ax.annotate(label, (rate, idx), xytext=(5, 0),
                    textcoords="offset points", va="center", ha="left",
                    fontsize=7.5, color=color,
                    fontweight="bold" if is_full else "normal")

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=7.6)
    ax.invert_yaxis()
    ax.set_xlim(*xlim)
    ax.set_xticks(tick_values)
    ax.set_xlabel("Overtaking success rate [%]", fontsize=8.2, labelpad=2.0)
    ax.tick_params(axis="x", labelsize=7.4, length=3.0, width=0.75)
    ax.tick_params(axis="y", length=0, pad=3.0)
    ax.grid(axis="x", color="0.88", lw=0.6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.set_title(title, loc="left", fontsize=8.7, fontweight="bold", pad=4.0)


def main() -> None:
    with SOURCE.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    comparison = data["comparison"]
    ablation = data["ablation"]
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 1.82))
    fig.subplots_adjust(left=0.15, right=0.992, bottom=0.24, top=0.88,
                        wspace=0.48)

    interval_panel(axes[0], comparison, "method", "a  Matched baselines",
                   (20.0, 101.0), [20, 40, 60, 80, 100])
    interval_panel(axes[1], ablation, "variant", "b  Component ablations",
                   (72.0, 101.0), [75, 80, 85, 90, 95, 100],
                   annotate_drops=True)

    fig.savefig(OUT.with_suffix(".svg"), facecolor="white")
    fig.savefig(OUT.with_suffix(".pdf"), facecolor="white")
    fig.savefig(OUT.with_suffix(".png"), dpi=600, facecolor="white")
    fig.savefig(OUT.with_suffix(".tiff"), dpi=600, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "axes.unicode_minus": True,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    main()
