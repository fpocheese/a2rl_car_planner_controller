"""
Generate Figure 16 and Figure 17 directly from the numerical values reported
in comparison_tables.tex.

The figures are aggregate multi-metric bar charts, not synthetic boxplots.
No random per-lap samples are generated.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


COMPARISON_METHODS = [
    "HG-Corridor\n(Ours)",
    "Pure\nRaceline",
    "Non-Interactive\nMPC",
    "Rule-based\nGT",
    "iLQGames",
]

COMPARISON_DATA = {
    "OSR [%]": [94.7, 38.2, 28.5, 51.6, 63.5],
    "TTO [s]": [4.82, 7.25, 11.23, 9.37, 7.83],
    "Mean Min Gap [m]": [5.83, 1.42, 3.85, 2.14, 2.31],
    "Collisions": [0, 21, 7, 48, 14],
    "Avg TTC [s]": [8.52, 3.21, 6.92, 5.64, 5.73],
    "PFR": [1.000, 0.988, 0.998, 0.987, 0.995],
}

ABLATION_METHODS = [
    "HG-Corridor",
    "w/o Game\nPrior",
    "w/o FSM",
    "w/o Learned\nCorr.",
    "SAC\n(vs. TQC)",
]

ABLATION_DATA = {
    "OSR [%]": [94.7, 85.4, 82.3, 76.1, 88.5],
    "TTO [s]": [4.82, 6.38, 6.71, 8.94, 5.53],
    "Mean Min Gap [m]": [5.83, 2.86, 2.17, 1.05, 3.94],
    "Collisions": [0, 9, 12, 31, 5],
    "Avg TTC [s]": [8.52, 4.93, 4.31, 2.86, 6.17],
    "PFR": [1.000, 0.983, 0.974, 0.961, 0.992],
}

METRIC_INFO = [
    ("OSR [%]", "higher is better", "{:.1f}", "#2E86AB"),
    ("TTO [s]", "lower is better", "{:.2f}", "#F18F01"),
    ("Mean Min Gap [m]", "higher is better", "{:.2f}", "#3C9D4E"),
    ("Collisions", "lower is better", "{:.0f}", "#C73E1D"),
    ("Avg TTC [s]", "higher is better", "{:.2f}", "#7B2CBF"),
    ("PFR", "higher is better", "{:.3f}", "#5A6C73"),
]


def _best_index(values, higher_is_better):
    arr = np.asarray(values, dtype=float)
    return int(np.argmax(arr) if higher_is_better else np.argmin(arr))


def _annotate_bars(ax, bars, values, fmt):
    ymax = max(values) if max(values) > 0 else 1.0
    offset = 0.03 * ymax
    for bar, value in zip(bars, values):
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            height + offset,
            fmt.format(value),
            ha="center",
            va="bottom",
            fontsize=7,
            rotation=0,
        )
    ax.set_ylim(0, ymax * 1.22 + offset)


def plot_table_summary(methods, data, out_path, title):
    fig, axes = plt.subplots(2, 3, figsize=(13.5, 6.8))
    axes = axes.ravel()
    x = np.arange(len(methods))

    for ax, (metric, direction, fmt, color) in zip(axes, METRIC_INFO):
        values = data[metric]
        higher = direction.startswith("higher")
        best = _best_index(values, higher)

        bars = ax.bar(x, values, color=color, alpha=0.78, edgecolor="black", linewidth=0.5)
        bars[best].set_alpha(1.0)
        bars[best].set_edgecolor("black")
        bars[best].set_linewidth(1.4)
        bars[best].set_hatch("//")

        _annotate_bars(ax, bars, values, fmt)
        ax.set_title(f"{metric} ({direction})", fontsize=10)
        ax.set_xticks(x)
        ax.set_xticklabels(methods, fontsize=7)
        ax.tick_params(axis="y", labelsize=8)
        ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.45)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    fig.suptitle(title, fontsize=12, y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.965])
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    plot_table_summary(
        COMPARISON_METHODS,
        COMPARISON_DATA,
        "figures/comparison_boxplot.pdf",
        "Comparative evaluation over 1000 closed-loop laps",
    )
    plot_table_summary(
        ABLATION_METHODS,
        ABLATION_DATA,
        "figures/ablation_boxplot.pdf",
        "Ablation study over 1000 closed-loop laps",
    )
