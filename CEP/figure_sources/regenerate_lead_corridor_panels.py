#!/usr/bin/env python3
"""Regenerate the two corridor panels with Lead-event subscripts."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib as mpl


fig_width_mm = 89.0


mpl.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "NewTX", "STIXGeneral"],
        "font.sans-serif": ["Arial", "Helvetica", "Liberation Sans"],
        "font.size": 8.0,
        "text.usetex": True,
        "text.latex.preamble": r"\usepackage{newtxtext,newtxmath}",
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "savefig.dpi": 600,
    }
)


def load_module(source: Path):
    spec = importlib.util.spec_from_file_location("corridor_panel_source", source)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load plotting source: {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def install_lead_annotations(module) -> None:
    def annotate_event_separations(axis, corridor, indices) -> None:
        for event_name, suffix in (("Encounter", "E"), ("Pass", "L")):
            index = indices[event_name]
            ego_x = float(corridor["ego_x"][index])
            ego_n = float(corridor["ego_n"][index])
            opponent_x = float(corridor["opponent_x"][index])
            opponent_n = float(corridor["opponent_n"][index])
            colour = module.v16.v10.EVENT_STYLE[event_name]["colour"]
            axis.annotate(
                rf"$\Delta s_{{\mathrm{{{suffix}}}}}$",
                xy=(0.5 * (ego_x + opponent_x), ego_n),
                xytext=(0.0, 3.0),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=7.2,
                color=colour,
                zorder=8,
            )
            lateral_offset = (
                (-3.0, 0.0) if event_name == "Encounter" else (3.0, 0.0)
            )
            lateral_align = "right" if event_name == "Encounter" else "left"
            axis.annotate(
                rf"$|\Delta n_{{\mathrm{{{suffix}}}}}|$",
                xy=(opponent_x, 0.5 * (ego_n + opponent_n)),
                xytext=lateral_offset,
                textcoords="offset points",
                ha=lateral_align,
                va="center",
                fontsize=7.2,
                color=colour,
                zorder=8,
            )

    module.v16.v12.annotate_event_separations = annotate_event_separations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_script", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    module = load_module(args.source_script.resolve())
    install_lead_annotations(module)
    cases, _ = module.v16.v7.load_two_measured_cases()
    panels = [module.build_corridor_panel(data) for data in cases]
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    crop = module.v16.common_tight_bbox([figure for figure, _ in panels])
    for figure, stem in panels:
        figure.savefig(output_dir / f"{stem}.svg", bbox_inches=crop, pad_inches=0)
        figure.savefig(output_dir / f"{stem}.pdf", bbox_inches=crop, pad_inches=0)
        figure.savefig(
            output_dir / f"{stem}.png", dpi=600, bbox_inches=crop, pad_inches=0
        )
        figure.savefig(
            output_dir / f"{stem}.tiff", dpi=600, bbox_inches=crop, pad_inches=0
        )


if __name__ == "__main__":
    main()
