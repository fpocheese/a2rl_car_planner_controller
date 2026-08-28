#!/usr/bin/env python3
"""Generate only V18 path-corridor panels with physical track boundaries."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np


sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
V16_SCRIPT = ROOT / "other_pic_V16" / "generate_case12_figures_v16.py"
SINGLE_DIR = OUT / "single_panels"

WIDTH_MM = 89.0
HEIGHT_MM = 57.0
PNG_DPI = 600
BOUNDARY_GREY = "#4A5056"


def load_v16_module():
    spec = importlib.util.spec_from_file_location("other_pic_v18_base", V16_SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load V16 plotting base: {V16_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


v16 = load_v16_module()
base = v16.base

# Retain the accepted V16/V17 LaTeX NewTX typography. NewTX intentionally
# replaces the validator's generic Arial/Helvetica recommendation.
plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["NewTX", "STIXGeneral", "DejaVu Serif"],
        "font.size": 8.0,
        "text.usetex": True,
        "text.latex.preamble": r"\usepackage{newtxtext,newtxmath}",
        "axes.unicode_minus": False,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "savefig.dpi": 600,
    }
)


def physical_boundaries(data) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Interpolate the recorded physical left/right bounds onto the plot grid."""
    (
        ego_x,
        _ego_n,
        _opponent_x,
        _opponent_n,
        _raw_lower,
        _raw_upper,
        physical_right,
        physical_left,
    ) = v16.v4.load_spatial_source(data)
    grid = np.asarray(data.display_corridor["grid"], dtype=float)
    if not np.all(np.diff(ego_x) > 0.0):
        raise ValueError(f"{data.source_case}: non-monotonic ego progress")
    right = np.interp(grid, ego_x, np.asarray(physical_right, dtype=float))
    left = np.interp(grid, ego_x, np.asarray(physical_left, dtype=float))
    if not (np.all(np.isfinite(left)) and np.all(np.isfinite(right))):
        raise ValueError(f"{data.source_case}: non-finite physical boundary")
    if np.any(right > left):
        raise ValueError(f"{data.source_case}: left/right physical bounds are inverted")
    return grid, left, right


def build_corridor_panel(data):
    fig, stem = v16.build_corridor_panel(data)
    if len(fig.axes) != 1:
        raise RuntimeError("V16 corridor panel should contain one axes")
    axis = fig.axes[0]
    grid, left, right = physical_boundaries(data)

    axis.plot(
        grid,
        left,
        color=BOUNDARY_GREY,
        linestyle=(0, (3.2, 2.0)),
        linewidth=0.78,
        zorder=2.8,
    )
    axis.plot(
        grid,
        right,
        color=BOUNDARY_GREY,
        linestyle=(0, (3.2, 2.0)),
        linewidth=0.78,
        zorder=2.8,
    )

    # Expand only when required to reveal a physical bound; retain V16's
    # existing top headroom for the in-axes legend and event annotations.
    y_low, y_high = axis.get_ylim()
    boundary_span = float(np.max(left) - np.min(right))
    margin = max(0.15, 0.025 * boundary_span)
    axis.set_ylim(
        min(y_low, float(np.min(right)) - margin),
        max(y_high, float(np.max(left)) + margin),
    )

    old_legend = axis.get_legend()
    if old_legend is not None:
        old_legend.remove()
    handles = v16.v12.corridor_legend_handles_v12()
    handles.extend(
        [
            Line2D(
                [],
                [],
                color=BOUNDARY_GREY,
                linestyle=(0, (3.2, 2.0)),
                linewidth=0.78,
                label="Track bound",
            ),
        ]
    )
    legend = axis.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.50, 0.950),
        ncol=4,
        fontsize=6.8,
        handlelength=1.00,
        handletextpad=0.25,
        columnspacing=0.48,
        labelspacing=0.25,
        borderaxespad=0.08,
        borderpad=0.30,
        frameon=True,
    )
    legend.get_frame().set_facecolor("white")
    legend.get_frame().set_edgecolor("none")
    legend.get_frame().set_alpha(0.95)
    return fig, stem


def save_corridor_group(items, directory: Path) -> None:
    crop = v16.common_tight_bbox([fig for fig, _stem in items])
    directory.mkdir(parents=True, exist_ok=True)
    for fig, stem in items:
        fig.savefig(
            directory / f"{stem}.png",
            dpi=600,
            facecolor="white",
            bbox_inches=crop,
            pad_inches=0,
        )
        plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SINGLE_DIR.mkdir(parents=True, exist_ok=True)
    cases, _limits = v16.v7.load_two_measured_cases()
    items = [build_corridor_panel(data) for data in cases]
    save_corridor_group(items, SINGLE_DIR)
    print(f"Generated V18 path-corridor panels in {SINGLE_DIR}")
    print("Both physical track bounds=grey dashed; one shared legend entry")


if __name__ == "__main__":
    main()
