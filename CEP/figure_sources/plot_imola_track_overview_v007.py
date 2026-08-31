#!/usr/bin/env python3
"""Render Imola overview v007 with panel letters ordered by display Case.

Figure contract
---------------
Core conclusion: four representative Imola overtakes are localized on the
track and paired with synchronized Shadow/Overtake simulator views.
Archetype: asymmetric mixed-modality figure.
Panel map: (a) track; (b,c) Case 1; (d,e) Case 2; (f,g) Case 3;
(h,i) Case 4.
Export: 100 x 82 mm, editable PDF/SVG and 600-dpi PNG.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


# The accepted overview uses NewTX serif to match the manuscript. Publication-
# safe Arial/Helvetica fallbacks are retained for generic renderer preflight.
plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["NewTX", "Times New Roman", "STIXGeneral", "DejaVu Serif"],
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "font.size": 8.0,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
    }
)


SOURCE_SCRIPT = Path(
    "/home/uav/11gsytset/0A_LYX_CODE/PAPER/car_pic/imola/"
    "overtake_campaign_20260826/code/plot_imola_track_overview_v006.py"
)
OUT = Path(__file__).resolve().parents[1]
FIGURE_WIDTH_MM = 100.0
FIGURE_HEIGHT_MM = 82.0
PNG_DPI = 600

# Recorded-case IDs are mapped to public-facing Cases by the accepted v006
# layout. Letters now follow that public-facing order rather than track order.
PANEL_LETTERS = {
    (12, 0): "b",
    (12, 1): "c",
    (1, 0): "d",
    (1, 1): "e",
    (11, 0): "f",
    (11, 1): "g",
    (10, 0): "h",
    (10, 1): "i",
}


def load_v006():
    spec = importlib.util.spec_from_file_location("imola_overview_v007_base", SOURCE_SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(SOURCE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


v006 = load_v006()
v004 = v006.v004
v003 = v006.v003
base = v006.base


def configure_v007():
    v006.configure_v006()
    v006.OUT = OUT
    v006.v005.OUT = OUT
    v004.OUT = OUT
    v003.OUT = OUT
    v004.PANEL_LETTERS = PANEL_LETTERS
    v003.PANEL_LETTERS = PANEL_LETTERS


def save_figure(snapshots, track):
    base.CASE_ACCENT = v004.CASE_ACCENT
    fig = plt.figure(
        figsize=(FIGURE_WIDTH_MM / 25.4, FIGURE_HEIGHT_MM / 25.4),
        facecolor="white",
    )
    overview_ax = fig.add_axes(v004.OVERVIEW_POSITION)
    v006.draw_overview(overview_ax, track, snapshots)

    for source_case in v004.CASE_ORDER:
        for panel in (0, 1):
            key = (source_case, panel)
            snapshot = snapshots[key]
            image_path = v003.SIMULATOR_DIR / (
                f"case_{source_case:02d}_{snapshot.phase.lower()}_annotated_v3.png"
            )
            if not image_path.is_file():
                raise FileNotFoundError(image_path)
            ax = fig.add_axes(v003.SIM_POSITIONS[key])
            v006.draw_simulator_panel(
                ax,
                image_path,
                PANEL_LETTERS[key],
                snapshot.phase,
                source_case,
            )
        v006.draw_case_title(fig, source_case)

    v003.draw_connectors(fig, overview_ax, snapshots)
    stem = OUT / "track_overview_imola_v007"
    export = {"facecolor": "white", "bbox_inches": "tight", "pad_inches": 0.0}
    fig.savefig(stem.with_suffix(".svg"), **export)
    fig.savefig(stem.with_suffix(".pdf"), **export)
    fig.savefig(stem.with_suffix(".png"), dpi=PNG_DPI, **export)
    plt.close(fig)
    return stem


def main():
    configure_v007()
    track = base.load_track()
    snapshots = v003.load_snapshots(track)
    stem = save_figure(snapshots, track)
    print(f"output={stem}")
    for source_case in v004.CASE_ORDER:
        display_case = v004.DISPLAY_CASE[source_case]
        print(
            f"Case {display_case}: "
            f"({PANEL_LETTERS[(source_case, 0)]}) Shadow, "
            f"({PANEL_LETTERS[(source_case, 1)]}) Overtake"
        )


if __name__ == "__main__":
    main()
