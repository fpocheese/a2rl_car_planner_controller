#!/usr/bin/env python3
"""Draw the single-column response-set-guided TQC training architecture."""

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle


OUT = Path(__file__).resolve().parent / "tqc_network_diagram"

mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
    "font.size": 7.0,
    "mathtext.fontset": "stixsans",
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "svg.fonttype": "none",
})

INK = "#26343D"
MUTED = "#63727C"
RULE = "#CAD3D9"
NAVY = "#295D8F"
TEAL = "#27796F"
PURPLE = "#76518D"
GOLD = "#B36A1D"
RED = "#C64A43"

PANEL = "#F8FAFB"
BLUE_FILL = "#EEF4F9"
TEAL_FILL = "#EDF7F4"
PURPLE_FILL = "#F5F0F7"
GOLD_FILL = "#FFF5E3"


def rounded(ax, x, y, w, h, *, face="white", edge=RULE, lw=0.85,
            radius=0.75, linestyle="-", zorder=2):
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0.015,rounding_size={radius}",
        facecolor=face, edgecolor=edge, linewidth=lw,
        linestyle=linestyle, zorder=zorder,
    )
    ax.add_patch(patch)
    return patch


def text_box(ax, x, y, w, h, lines, *, face="white", edge=RULE,
             lw=0.85, linestyle="-", radius=0.75):
    rounded(ax, x, y, w, h, face=face, edge=edge, lw=lw,
            radius=radius, linestyle=linestyle, zorder=3)
    if isinstance(lines, str):
        lines = [(lines, 6.6, "normal", INK)]
    step = h / (len(lines) + 1)
    for i, (txt, size, weight, color) in enumerate(lines, start=1):
        ax.text(x + w / 2, y + h - i * step, txt,
                fontsize=size, fontweight=weight, color=color,
                ha="center", va="center", linespacing=1.0, zorder=5)


def arrow(ax, start, end, *, color=INK, lw=0.9, style="-", curve="arc3",
          zorder=4):
    ax.add_patch(FancyArrowPatch(
        start, end, arrowstyle="-|>", mutation_scale=6.6,
        linewidth=lw, linestyle=style, color=color,
        connectionstyle=curve, shrinkA=1.2, shrinkB=1.2, zorder=zorder,
    ))


def route(ax, points, *, color=INK, lw=0.85, style="-", zorder=2):
    xs, ys = zip(*points)
    ax.plot(xs[:-1], ys[:-1], color=color, linewidth=lw,
            linestyle=style, solid_capstyle="round", zorder=zorder)
    arrow(ax, points[-2], points[-1], color=color, lw=lw, style=style,
          zorder=zorder + 1)


def lane(ax, y, h, title, color):
    rounded(ax, 1.2, y, 97.6, h, face=PANEL, edge=RULE, lw=0.65,
            radius=0.9, zorder=0)
    ax.text(4.0, y + h - 3.4, title, fontsize=6.4, fontweight="bold",
            color=color, ha="left", va="center", zorder=6)


def atom_strip(ax, x, y):
    """Compact symbolic rendering of sorted TQC atoms."""
    n, keep = 16, 14
    width, gap, height = 1.55, 0.28, 3.2
    for i in range(n):
        x0 = x + i * (width + gap)
        discarded = i >= keep
        edge = RED if discarded else NAVY
        face = "#F8DFDC" if discarded else "#DCEAF5"
        ax.add_patch(Rectangle(
            (x0, y), width, height, facecolor=face, edgecolor=edge,
            linewidth=0.55, zorder=5,
        ))
        if discarded:
            ax.plot([x0 + 0.18, x0 + width - 0.18],
                    [y + 0.25, y + height - 0.25], color=RED,
                    linewidth=0.55, zorder=6)
            ax.plot([x0 + 0.18, x0 + width - 0.18],
                    [y + height - 0.25, y + 0.25], color=RED,
                    linewidth=0.55, zorder=6)


def main():
    # Elsevier single-column width (88.4 mm), compact portrait layout.
    fig, ax = plt.subplots(figsize=(3.48, 4.02))
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 116)
    ax.axis("off")

    lane(ax, 92.0, 22.5, "RESPONSE-SET SUPERVISION", PURPLE)
    lane(ax, 62.0, 27.0, "ACTOR UPDATE  |  INDEPENDENT ENCODER", NAVY)
    lane(ax, 25.0, 34.0, "CRITIC UPDATE  |  SHARED ENCODER", TEAL)
    lane(ax, 1.5, 20.5, "TRUNCATED DISTRIBUTIONAL TARGET", NAVY)

    # Offline teacher: the two outputs have deliberately different roles.
    text_box(ax, 4.0, 96.0, 24.0, 11.5, [
        ("Robust Stackelberg", 5.3, "bold", INK),
        ("response-set", 5.3, "bold", INK),
        ("teacher", 5.3, "bold", INK),
    ], face=PURPLE_FILL, edge=PURPLE, lw=0.95)
    text_box(ax, 34.0, 100.5, 26.0, 7.5, [
        ("Response-set-optimal prior", 5.3, "normal", INK),
        (r"$\mathbf{a}_{\rm th}^{\star}$", 8.0, "normal", INK),
    ], edge=PURPLE)
    text_box(ax, 64.0, 95.5, 32.0, 9.0, [
        ("Matched teacher set", 5.6, "normal", INK),
        (r"$\mathcal{D}_g:(\widetilde{\mathbf{o}}_g,\mathbf{a}_g^{\rm F},v_g)$",
         7.0, "normal", INK),
    ], edge=PURPLE)
    arrow(ax, (28.0, 103.7), (34.0, 104.2), color=PURPLE)
    arrow(ax, (28.0, 99.3), (64.0, 99.8), color=PURPLE)

    # Actor branch. The critic supplies the projected-action Q gradient.
    text_box(ax, 4.0, 69.0, 12.0, 11.0, [
        (r"$\widetilde{\mathbf{o}}$", 8.0, "normal", INK),
        ("51-D", 5.7, "normal", MUTED),
    ], face=BLUE_FILL, edge=NAVY)
    text_box(ax, 21.0, 67.0, 23.0, 15.0, [
        ("Actor encoder", 6.0, "bold", INK),
        (r"$\mathcal{E}^{\pi}_{\theta}$", 8.0, "normal", INK),
        ("independent", 5.6, "normal", MUTED),
    ], face="white", edge=NAVY, lw=0.95)
    text_box(ax, 49.0, 67.0, 20.0, 15.0, [
        ("Projected mean", 5.7, "normal", INK),
        (r"$\mu^{\rm raw}\!\rightarrow\!"
         r"\mu^{\rm B}\!\rightarrow\!"
         r"\mu^{\rm F,ST}$", 6.8, "normal", INK),
        (r"$\Pi_{\mathcal{A}}$ exact; $\Pi_{\rm tire}$ STE", 5.7, "normal", MUTED),
    ], face=GOLD_FILL, edge=GOLD)
    text_box(ax, 76.0, 67.0, 20.0, 15.0, [
        ("Actor objective", 5.1, "bold", INK),
        (r"$\mathcal{L}_{\rm actor}$", 7.7, "normal", INK),
        (r"$=J_\pi+\lambda_p\mathcal{L}_p$", 6.8, "normal", INK),
    ], face="white", edge=NAVY, lw=0.95)
    arrow(ax, (16.0, 74.5), (21.0, 74.5), color=NAVY)
    arrow(ax, (44.0, 74.5), (49.0, 74.5), color=NAVY)
    arrow(ax, (69.0, 74.5), (76.0, 74.5), color=NAVY)
    route(ax, [(47.0, 100.5), (47.0, 91.0), (72.0, 91.0),
               (72.0, 84.0), (86.0, 84.0), (86.0, 82.0)],
          color=PURPLE, lw=0.85)
    ax.text(78.0, 83.3, "action prior", fontsize=5.4, color=PURPLE,
            ha="center", va="top")
    ax.text(59.0, 64.8, r"$Q$: $\mathbf{a}^{\rm F,ST}$   |   entropy: $\mathbf{a}^{\rm raw}$",
            fontsize=5.8, color=MUTED, ha="center", va="center")

    # Critic branch: environment replay and matched teacher labels share only
    # the critic-side representation.
    text_box(ax, 4.0, 36.0, 16.0, 13.5, [
        (r"Replay $\mathcal{D}$", 6.1, "bold", INK),
        ("stores exact", 5.3, "normal", MUTED),
        (r"$\mathbf{a}^{\rm F}$", 7.8, "normal", INK),
    ], face=BLUE_FILL, edge=NAVY)
    text_box(ax, 25.0, 34.0, 25.0, 17.0, [
        ("Shared critic encoder", 5.2, "bold", INK),
        (r"$\mathcal{E}^Q_{\zeta}$", 7.3, "normal", INK),
        (r"$(\widetilde{\mathbf{o}},\mathbf{a}^{\rm F})$", 7.3, "normal", INK),
    ], face=TEAL_FILL, edge=TEAL, lw=0.95)
    text_box(ax, 55.0, 44.0, 14.5, 7.5, [
        (r"$Q_1$: 25 atoms", 5.2, "normal", INK),
    ], edge=TEAL)
    text_box(ax, 55.0, 35.0, 14.5, 7.5, [
        (r"$Q_2$: 25 atoms", 5.2, "normal", INK),
    ], edge=TEAL)
    text_box(ax, 55.0, 26.5, 13.0, 7.0, [
        (r"$g_\psi$: value", 6.1, "normal", INK),
        ("training only", 5.1, "normal", PURPLE),
    ], face=PURPLE_FILL, edge=PURPLE, linestyle=(0, (3, 2)))
    text_box(ax, 76.0, 34.0, 20.0, 17.0, [
        ("Critic objective", 5.1, "bold", INK),
        (r"$\mathcal{L}_{\rm critic}$", 7.5, "normal", INK),
        (r"$=J_Q+\lambda_g\mathcal{L}_g$", 6.6, "normal", INK),
    ], face="white", edge=TEAL, lw=0.95)
    arrow(ax, (20.0, 42.5), (25.0, 42.5), color=TEAL)
    arrow(ax, (50.0, 46.0), (55.0, 47.7), color=TEAL)
    arrow(ax, (50.0, 41.5), (55.0, 38.7), color=TEAL)
    arrow(ax, (50.0, 37.0), (55.0, 30.0), color=PURPLE)
    arrow(ax, (69.5, 47.7), (76.0, 46.0), color=TEAL)
    arrow(ax, (69.5, 38.7), (76.0, 40.0), color=TEAL)
    arrow(ax, (68.0, 30.0), (79.0, 34.0), color=PURPLE)

    # D_g actions enter the same critic encoder; their matched values supervise
    # the scalar head through the auxiliary objective.
    route(ax, [(96.0, 100.0), (97.5, 93.0), (97.5, 53.0),
               (50.5, 53.0), (50.5, 46.0)],
          color=PURPLE, lw=0.85)
    ax.text(69.0, 53.7, "matched action--value pairs", fontsize=5.4,
            color=PURPLE, ha="center", va="bottom")

    # Quantile critics provide the actor's projected-action Q gradient.
    route(ax, [(69.5, 48.8), (72.0, 48.8), (72.0, 61.0),
               (91.5, 61.0), (91.5, 67.0)], color=NAVY, lw=0.85)
    ax.text(80.5, 61.8, r"projected-action $J_\pi$", fontsize=5.4,
            color=NAVY, ha="center", va="bottom")

    # Standard TQC target: pool, sort, and remove the largest four atoms.
    text_box(ax, 4.0, 6.0, 17.0, 9.5, [
        ("Target", 5.5, "bold", INK),
        ("critics", 5.5, "bold", INK),
        (r"$2N_q=50$", 7.1, "normal", INK),
    ], face=BLUE_FILL, edge=NAVY)
    atom_strip(ax, 27.0, 9.2)
    ax.text(41.0, 16.7, "sort 50 atoms", fontsize=5.2, color=MUTED,
            ha="center", va="center")
    ax.text(40.0, 6.2, r"retain $K=46$", fontsize=6.2, color=NAVY,
            ha="center", va="center")
    ax.text(56.5, 16.7, "drop largest 4", fontsize=5.2, color=RED,
            ha="center", va="center")
    text_box(ax, 76.0, 6.0, 20.0, 9.5, [
        ("Detached", 5.5, "bold", INK),
        ("target", 5.5, "bold", INK),
        (r"$\mathcal{Y}_t=\operatorname{sg}[\,\cdot\,]$", 6.6, "normal", INK),
    ], edge=NAVY)
    arrow(ax, (21.0, 10.7), (27.0, 10.7), color=INK, lw=0.8)
    arrow(ax, (57.0, 10.7), (76.0, 10.7), color=INK, lw=0.8)
    route(ax, [(86.0, 15.5), (86.0, 25.0), (90.0, 25.0), (90.0, 34.0)],
          color=INK, lw=0.8)
    route(ax, [(12.5, 36.0), (12.5, 22.5), (12.5, 15.5)],
          color=INK, lw=0.8)

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
