#!/usr/bin/env python3
"""Generate publication figures for the implemented pure-slip tire model."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np


# Parameters extracted from src/a2rl_pnc/vn_transformer/src/vn_transformer.cpp.
# The original implementation names mu and load_slope as D and D2,
# respectively, and computes B from the specified peak-slip location.
FZ_NOM = 2079.72  # N
PACEJKA_PARAMS = {
    "x": {
        "C": 1.6144,
        "E": 0.0,
        "mu": 2.2345,
        "load_slope": -0.2555,
        "peak_slip": 0.12960000336170197,
    },
    "y": {
        "C": 1.5998,
        "E": 0.0,
        "mu": 1.9745,
        "load_slope": -0.4787,
        "peak_slip": 0.140,
    },
}
FZ_VALUES = (2000.0, 3000.0, 4000.0, 5000.0, 6000.0, 7000.0)  # N
OUTPUT_DIR = Path(__file__).resolve().parent


def shape_factor_b(axis: str) -> float:
    """Return B using the peak-slip construction in the vehicle model."""
    params = PACEJKA_PARAMS[axis]
    return np.tan(np.pi / (2.0 * params["C"])) / params["peak_slip"]


def peak_force(axis: str, f_z: float) -> float:
    """Return the load-dependent Magic Formula peak term D_j(F_z) in N."""
    params = PACEJKA_PARAMS[axis]
    f_z_clamped = np.clip(f_z, FZ_NOM / 3.0, 3.0 * FZ_NOM)
    mu_effective = (
        params["mu"]
        + params["load_slope"] * (f_z_clamped - FZ_NOM) / FZ_NOM
    )
    return f_z * mu_effective


def magic_formula(axis: str, slip: np.ndarray, f_z: float) -> np.ndarray:
    """Evaluate F_j(q_j,F_z) for pure longitudinal or pure lateral slip."""
    params = PACEJKA_PARAMS[axis]
    b_value = shape_factor_b(axis)
    bq = b_value * np.asarray(slip)
    phase = bq - params["E"] * (bq - np.arctan(bq))
    return peak_force(axis, f_z) * np.sin(params["C"] * np.arctan(phase))


def style_axes(ax: plt.Axes) -> None:
    ax.axhline(0.0, color="0.25", linewidth=0.65, zorder=0)
    ax.axvline(0.0, color="0.25", linewidth=0.65, zorder=0)
    ax.grid(True, color="0.82", linestyle="--", linewidth=0.45, alpha=0.8)
    ax.tick_params(axis="both", which="major", labelsize=7.5, length=3.0)
    for spine in ax.spines.values():
        spine.set_linewidth(0.7)


def save_figure(fig: plt.Figure, stem: str) -> None:
    fig.savefig(
        OUTPUT_DIR / f"{stem}.svg",
        bbox_inches="tight",
        pad_inches=0.025,
    )
    fig.savefig(
        OUTPUT_DIR / f"{stem}.pdf",
        bbox_inches="tight",
        pad_inches=0.025,
    )
    fig.savefig(
        OUTPUT_DIR / f"{stem}.png",
        dpi=600,
        bbox_inches="tight",
        pad_inches=0.025,
    )
    fig.savefig(
        OUTPUT_DIR / f"{stem}.tiff",
        dpi=600,
        bbox_inches="tight",
        pad_inches=0.025,
    )
    plt.close(fig)


def save_fixed_size_figure(fig: plt.Figure, stem: str) -> None:
    """Export a composite at its declared single-column physical size."""
    fig.savefig(OUTPUT_DIR / f"{stem}.svg", facecolor="white")
    fig.savefig(OUTPUT_DIR / f"{stem}.pdf", facecolor="white")
    fig.savefig(OUTPUT_DIR / f"{stem}.png", dpi=600, facecolor="white")
    fig.savefig(OUTPUT_DIR / f"{stem}.tiff", dpi=600, facecolor="white")
    plt.close(fig)


def plot_force_curve(axis: str, slip: np.ndarray, xlabel: str, ylabel: str,
                     output_stem: str) -> None:
    fig, ax = plt.subplots(figsize=(3.35, 2.05))
    colors = plt.get_cmap("viridis")(np.linspace(0.12, 0.88, len(FZ_VALUES)))
    for f_z, color in zip(FZ_VALUES, colors):
        force_kn = magic_formula(axis, slip, f_z) / 1000.0
        ax.plot(
            slip,
            force_kn,
            color=color,
            linewidth=1.45,
            label=rf"$F_z={f_z / 1000.0:g}\,\mathrm{{kN}}$",
        )

    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_xlim(float(slip[0]), float(slip[-1]))
    style_axes(ax)
    ax.legend(
        loc="best",
        fontsize=8.0,
        frameon=True,
        framealpha=0.92,
        edgecolor="0.75",
        borderpad=0.35,
        handlelength=1.8,
    )
    fig.tight_layout(pad=0.35)
    save_figure(fig, output_stem)


def plot_combined_force_curves() -> None:
    """Place the longitudinal and lateral relations in a compact 1-by-2 panel."""
    fig, axes = plt.subplots(1, 2, figsize=(3.35, 1.62))
    fig.subplots_adjust(left=0.125, right=0.955, bottom=0.245, top=0.755,
                        wspace=0.43)

    cmap = plt.get_cmap("viridis")
    norm = mpl.colors.Normalize(vmin=2.0, vmax=7.0)
    colors = cmap(norm(np.asarray(FZ_VALUES) / 1000.0))
    panels = (
        ("x", np.linspace(-0.5, 0.5, 1001), "λ", "Fx (kN)"),
        ("y", np.linspace(-0.5, 0.5, 1001), "αt (rad)", "Fy (kN)"),
    )
    for panel_label, ax, (axis, slip, xlabel, ylabel) in zip(
            ("a", "b"), axes, panels):
        for f_z, color in zip(FZ_VALUES, colors):
            ax.plot(slip, magic_formula(axis, slip, f_z) / 1000.0,
                    color=color, linewidth=0.95)
        ax.set_xlabel(xlabel, fontsize=7.6, labelpad=1.5)
        ax.set_ylabel(ylabel, fontsize=7.6, labelpad=1.5)
        ax.set_xlim(float(slip[0]), float(slip[-1]))
        style_axes(ax)
        ax.tick_params(axis="both", which="major", labelsize=6.7,
                       length=2.4, pad=1.6)
        ax.text(0.025, 0.965, panel_label, transform=ax.transAxes,
                fontsize=8.0, fontweight="bold", va="top", ha="left")

    colorbar_ax = fig.add_axes([0.38, 0.865, 0.555, 0.035])
    colorbar = mpl.colorbar.ColorbarBase(
        colorbar_ax, cmap=cmap, norm=norm, orientation="horizontal",
        ticks=np.arange(2.0, 8.0, 1.0),
    )
    colorbar.ax.tick_params(labelsize=6.4, length=2.0, pad=1.0)
    colorbar.ax.set_title("Vertical load Fz (kN)", fontsize=7.6, pad=1.2)
    colorbar.outline.set_linewidth(0.55)

    save_fixed_size_figure(fig, "tire_force_characteristics")


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
    plot_force_curve(
        "x",
        np.linspace(-0.5, 0.5, 1001),
        r"$\lambda$",
        r"$F_x$ (kN)",
        "tire_longitudinal_magic_formula",
    )
    plot_force_curve(
        "y",
        np.linspace(-0.5, 0.5, 1001),
        r"$\alpha_{\rm t}$ (rad)",
        r"$F_y$ (kN)",
        "tire_lateral_magic_formula",
    )
    plot_combined_force_curves()


if __name__ == "__main__":
    main()
