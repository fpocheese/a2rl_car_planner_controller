#!/usr/bin/env python3
"""Render a publication-ready single-column game-guided TQC schematic."""

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle


OUT = Path(__file__).resolve().parent / "tqc_network_diagram"

mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
    "font.size": 7.2,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "svg.fonttype": "none",
})

INK = "#28333C"
GREY = "#68747E"
EDGE = "#D2D9DF"
BLUE = "#285F9E"
TEAL = "#28776D"
PURPLE = "#76538D"
ORANGE = "#B86A18"
RED = "#C54B45"
BLUE_BG = "#EEF4FA"
TEAL_BG = "#EEF7F4"
PURPLE_BG = "#F6F1F8"


def panel(ax, y, h, title, color, face):
    ax.add_patch(FancyBboxPatch(
        (1.1, y), 97.8, h,
        boxstyle="round,pad=0.012,rounding_size=0.75",
        facecolor=face, edgecolor=EDGE, linewidth=0.75, zorder=0,
    ))
    ax.text(3.2, y + h - 3.6, title, fontsize=7.1, fontweight="bold",
            color=color, ha="left", va="center", zorder=6)


def box(ax, x, y, w, h, text, *, edge=GREY, face="white", fontsize=7.2,
        linestyle="-", linewidth=0.9, fontweight="normal", color=INK):
    if "$" in text:
        fontsize = max(fontsize, 7.2)
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.014,rounding_size=0.58",
        facecolor=face, edgecolor=edge, linewidth=linewidth,
        linestyle=linestyle, zorder=3,
    ))
    ax.text(x + w / 2, y + h / 2, text, fontsize=fontsize,
            fontweight=fontweight, color=color, ha="center", va="center",
            linespacing=1.05, zorder=5)


def line_box(ax, x, y, w, h, lines, *, edge=GREY, face="white",
             linestyle="-", linewidth=0.9):
    """Draw a box whose plain-text and math lines can use different sizes."""
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.014,rounding_size=0.58",
        facecolor=face, edgecolor=edge, linewidth=linewidth,
        linestyle=linestyle, zorder=3,
    ))
    step = h / (len(lines) + 1)
    for i, (text, fontsize, weight, color) in enumerate(lines, start=1):
        ax.text(x + w / 2, y + h - i * step, text, fontsize=fontsize,
                fontweight=weight, color=color, ha="center", va="center",
                zorder=5)


def network_box(ax, x, y, w, h, title, subtitle, color):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.014,rounding_size=0.58",
        facecolor="white", edgecolor=color, linewidth=1.0, zorder=3,
    ))
    for col, count in [(x + 2.2, 3), (x + 4.3, 4), (x + 6.4, 3)]:
        for j in range(count):
            cy = y + 2.0 + j * (h - 4.0) / (count - 1)
            ax.add_patch(Circle((col, cy), 0.42, facecolor="white",
                                edgecolor=color, linewidth=0.6, zorder=4))
    ax.text(x + 7.9, y + h * 0.61, title, fontsize=7.1, fontweight="bold",
            color=INK, ha="left", va="center", zorder=5)
    subtitle_size = 7.2 if "$" in subtitle else 6.1
    ax.text(x + 7.9, y + h * 0.34, subtitle, fontsize=subtitle_size, color=GREY,
            ha="left", va="center", zorder=5)


def arrow(ax, start, end, *, color=INK, lw=0.9, linestyle="-",
          curve="arc3", zorder=2):
    ax.add_patch(FancyArrowPatch(
        start, end, arrowstyle="-|>", mutation_scale=6.8,
        linewidth=lw, linestyle=linestyle, color=color,
        connectionstyle=curve, shrinkA=1.0, shrinkB=1.0, zorder=zorder,
    ))


def routed_arrow(ax, points, *, color=INK, lw=0.9, linestyle="-", zorder=1):
    """Draw an orthogonal connector with an arrowhead on the last segment."""
    xs, ys = zip(*points)
    ax.plot(xs[:-1], ys[:-1], color=color, linewidth=lw,
            linestyle=linestyle, solid_capstyle="round", zorder=zorder)
    arrow(ax, points[-2], points[-1], color=color, lw=lw,
          linestyle=linestyle, zorder=zorder + 0.1)


def atom_strip(ax, x, y, n=18):
    """Symbolic sorted atoms; the final pair represents discarded upper atoms."""
    width, gap, discarded = 1.20, 0.32, 2
    for i in range(n):
        is_discarded = i >= n - discarded
        edge = RED if is_discarded else BLUE
        face = "#F8DEDB" if is_discarded else "#DCEAF5"
        x0 = x + i * (width + gap)
        ax.add_patch(Rectangle((x0, y), width, 3.0, facecolor=face,
                               edgecolor=edge, linewidth=0.55, zorder=4))
        if is_discarded:
            ax.plot([x0 + 0.16, x0 + width - 0.16], [y + 0.22, y + 2.78],
                    color=RED, linewidth=0.55, zorder=5)
            ax.plot([x0 + 0.16, x0 + width - 0.16], [y + 2.78, y + 0.22],
                    color=RED, linewidth=0.55, zorder=5)


def main():
    # 88.4 mm wide and approximately 106 mm high at final print size.
    fig, ax = plt.subplots(figsize=(3.48, 4.18))
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 120)
    ax.axis("off")

    panel(ax, 93.0, 25.0, "Online tactical publication", BLUE, BLUE_BG)
    panel(ax, 64.0, 25.0, "Offline response-set supervision", PURPLE, PURPLE_BG)
    panel(ax, 2.0, 58.0, "Projected-action TQC", TEAL, TEAL_BG)

    # Online path: actor -> ordered projection -> deterministic publisher.
    box(ax, 3.5, 100.0, 9.0, 10.0, "State\n$\\widetilde{\\mathbf{o}}$",
        edge=GREY)
    network_box(ax, 15.5, 98.0, 17.0, 14.0,
                "Actor", "$\\pi_\\theta$", BLUE)
    box(ax, 35.5, 98.0, 21.0, 14.0,
        "$\\mathbf{a}^{\\rm raw}$\n$\\Pi_{\\mathcal{A}}$\n"
        "$\\mathbf{a}^{\\rm B}$",
        edge=ORANGE, face="#FFF5DF", fontsize=7.2)
    ax.text(46.0, 96.3, "bound + order", fontsize=5.9, color=ORANGE,
            ha="center", va="center")
    line_box(ax, 59.5, 96.0, 20.5, 18.0, [
        ("Publisher", 6.0, "normal", INK),
        ("$\\mathcal{F}_h$", 7.2, "normal", INK),
        ("FSM $\\cdot$ carver", 5.8, "normal", INK),
        ("$\\Pi_{\\rm tire}$", 7.2, "normal", INK),
        ("fallback", 5.8, "normal", INK),
    ], edge=TEAL, face="#EDF6EC")
    box(ax, 83.0, 105.0, 13.5, 7.5, "$\\mathbf{a}^{\\rm F}$",
        edge=TEAL, fontsize=7.8)
    box(ax, 83.0, 96.0, 13.5, 7.0, "$\\mathcal{G}_t$",
        edge=TEAL, fontsize=7.8)
    arrow(ax, (12.5, 105.0), (15.5, 105.0), color=BLUE, lw=1.0)
    arrow(ax, (32.5, 105.0), (35.5, 105.0), color=BLUE, lw=1.0)
    arrow(ax, (56.5, 105.0), (59.5, 105.0), color=TEAL, lw=1.0)
    arrow(ax, (80.0, 108.7), (83.0, 108.7), color=TEAL, lw=1.0)
    arrow(ax, (80.0, 99.5), (83.0, 99.5), color=TEAL, lw=1.0)
    ax.text(89.8, 94.3, "to executor", fontsize=6.0, color=GREY,
            ha="center", va="center")

    # Teacher outputs: an optimal projected prior and matched value labels.
    box(ax, 3.5, 70.0, 20.0, 10.5, "Response-set\nteacher",
        edge=PURPLE, face="#EDE3F2", fontsize=5.8, fontweight="bold")
    box(ax, 26.5, 73.0, 19.0, 9.0,
        "Action prior\n$\\mathbf{a}_{\\rm th}^{\\star}$",
        edge=PURPLE, fontsize=6.4)
    box(ax, 26.5, 64.8, 32.5, 7.2,
        "Matched $\\mathcal{D}_g\\ne\\mathcal{D}$\n"
        "$(\\widetilde{\\mathbf{o}}_g,\\mathbf{a}_g^{\\rm F},v_g)$",
        edge=PURPLE, fontsize=6.2)
    line_box(ax, 65.0, 69.0, 31.0, 15.5, [
        ("Actor update", 6.2, "normal", INK),
        ("$J_\\pi+\\lambda_p\\mathcal{L}_p$", 7.2, "normal", INK),
        ("$Q:\\;\\mathbf{a}^{\\rm F,ST}$", 7.2, "normal", INK),
        ("$\\mathrm{entropy}:\\;\\mathbf{a}^{\\rm raw}$", 7.2, "normal", INK),
    ], edge=ORANGE, face="#FFF4DD")
    arrow(ax, (23.5, 76.5), (26.5, 77.5), color=PURPLE, lw=0.9)
    arrow(ax, (23.5, 72.0), (26.5, 68.4), color=PURPLE, lw=0.9)
    arrow(ax, (45.5, 77.5), (65.0, 77.5), color=PURPLE, lw=0.9)

    # Straight-through surrogate only for actor/prior gradients.
    routed_arrow(ax,
                 [(89.8, 105.0), (98.0, 105.0), (98.0, 91.0),
                  (89.0, 91.0), (89.0, 84.5)],
                 color=ORANGE, lw=0.85, linestyle=(0, (4, 2)), zorder=2)
    ax.text(93.6, 92.1, "STE", fontsize=6.2, color=ORANGE,
            ha="center", va="center")

    # Main critic path.
    line_box(ax, 4.0, 34.5, 16.0, 14.0, [
        ("$\\mathrm{Replay}\\;\\mathcal{D}$", 7.2, "normal", INK),
        ("stores", 5.8, "normal", INK),
        ("exact", 5.8, "normal", INK),
        ("$\\mathbf{a}^{\\rm F}$", 7.2, "bold", INK),
    ], edge=BLUE, face="#E8F0F8")
    network_box(ax, 24.0, 34.0, 23.0, 15.5,
                "Shared", "encoder", TEAL)
    line_box(ax, 51.0, 42.0, 15.0, 7.5, [
        ("Head 1", 6.0, "normal", INK),
        ("$N_q=25$", 7.2, "normal", INK),
    ], edge=TEAL)
    line_box(ax, 51.0, 33.5, 15.0, 7.0, [
        ("Head 2", 6.0, "normal", INK),
        ("$N_q=25$", 7.2, "normal", INK),
    ], edge=TEAL)
    line_box(ax, 51.0, 22.5, 15.0, 9.5, [
        ("Value head", 5.8, "normal", INK),
        ("$g_\\psi$", 7.2, "normal", INK),
        ("training only", 5.8, "normal", INK),
    ], edge=PURPLE, face="#F2EAF5", linestyle=(0, (4, 2)))
    line_box(ax, 78.0, 33.5, 18.0, 16.0, [
        ("Critic", 6.0, "bold", INK),
        ("update", 6.0, "bold", INK),
        ("$J_Q+\\lambda_g\\mathcal{L}_g$", 7.2, "normal", INK),
    ], edge=TEAL)
    arrow(ax, (20.0, 42.0), (24.0, 42.0), color=TEAL, lw=1.0)
    arrow(ax, (47.0, 45.0), (51.0, 45.8), color=TEAL, lw=0.9)
    arrow(ax, (47.0, 39.0), (51.0, 37.0), color=TEAL, lw=0.9)
    arrow(ax, (47.0, 35.5), (51.0, 27.3), color=PURPLE, lw=0.9)
    arrow(ax, (66.0, 45.8), (78.0, 44.5), color=TEAL, lw=0.9)
    arrow(ax, (66.0, 37.0), (78.0, 39.5), color=TEAL, lw=0.9)
    arrow(ax, (66.0, 27.3), (84.0, 33.5), color=PURPLE, lw=0.9)

    # Matched teacher tuples use the same critic encoder but not replay D.
    routed_arrow(ax,
                 [(42.5, 64.8), (49.0, 62.0), (49.0, 43.0), (47.0, 43.0)],
                 color=PURPLE, lw=0.9, zorder=2)
    ax.text(50.3, 57.0, "$\\mathcal{D}_g$", fontsize=7.2, color=PURPLE,
            ha="left", va="center")

    # The projected-action critic supplies J_pi to the actor update.
    routed_arrow(ax,
                 [(66.0, 47.0), (71.0, 47.0), (71.0, 62.0),
                  (80.5, 62.0), (80.5, 69.0)],
                 color=BLUE, lw=0.9, zorder=1)
    ax.text(76.0, 62.0, "$J_\\pi$", fontsize=7.2, color=BLUE,
            ha="center", va="bottom")

    # Exact a^F is the only action stored in environment replay.
    routed_arrow(ax,
                 [(96.5, 108.7), (98.5, 108.7), (98.5, 62.0),
                  (2.5, 62.0), (2.5, 51.0), (12.0, 51.0), (12.0, 48.5)],
                 color=TEAL, lw=0.95, zorder=1)

    # Target-critic branch and TQC truncation.
    line_box(ax, 4.0, 7.0, 16.0, 11.5, [
        ("Target", 5.8, "normal", INK),
        ("critics", 5.8, "normal", INK),
        ("$2N_q=50$", 7.2, "normal", INK),
    ], edge=BLUE, face="#E8F0F8")
    routed_arrow(ax, [(12.0, 34.5), (12.0, 18.5)], color=INK, lw=0.8)
    atom_strip(ax, 25.0, 11.2, n=18)
    arrow(ax, (20.0, 12.7), (25.0, 12.7), color=INK, lw=0.85)
    ax.text(38.5, 16.8, "pool and sort", fontsize=6.0, color=GREY,
            ha="center", va="center")
    ax.text(38.5, 7.5, "retain $K=46$", fontsize=7.2, color=BLUE,
            ha="center", va="center")
    ax.text(62.5, 16.8, "discard 4", fontsize=6.0, color=RED,
            ha="center", va="center")
    line_box(ax, 77.0, 7.0, 19.0, 11.5, [
        ("Detached", 5.8, "normal", INK),
        ("target", 5.8, "normal", INK),
        ("$\\mathcal{Y}_t=\\operatorname{sg}[\\,\\cdot\\,]$", 7.2, "normal", INK),
    ], edge=BLUE)
    arrow(ax, (53.0, 12.7), (77.0, 12.7), color=INK, lw=0.85)
    routed_arrow(ax,
                 [(86.5, 18.5), (86.5, 25.0), (90.0, 25.0), (90.0, 33.5)],
                 color=INK, lw=0.85, zorder=1)

    fig.savefig(OUT.with_suffix(".svg"), bbox_inches="tight", pad_inches=0.02)
    fig.savefig(OUT.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.02)
    fig.savefig(OUT.with_suffix(".png"), dpi=300,
                bbox_inches="tight", pad_inches=0.02)
    fig.savefig(OUT.with_suffix(".tiff"), dpi=600,
                bbox_inches="tight", pad_inches=0.02,
                pil_kwargs={"compression": "tiff_lzw"})
    plt.close(fig)


if __name__ == "__main__":
    main()
