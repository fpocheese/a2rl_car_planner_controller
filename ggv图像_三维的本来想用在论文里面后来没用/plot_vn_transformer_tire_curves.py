#!/usr/bin/env python3
"""Plot tire force curves with publication-quality PNG output."""

import numpy as np
import matplotlib.pyplot as plt

# Tire model parameters extracted from src/a2rl_pnc/vn_transformer/src/vn_transformer.cpp
# Both front and rear use the same Pacejka parameters here.
PACEJKA_PARAMS = {
    "FzNom": 2079.72,
    "Cx": 1.6144,
    "Cy": 1.5998,
    "Dx": 2.2345,
    "Dy": 1.9745,
    "Dx2": -0.2555,
    "Dy2": -0.4787,
    "sxPeak": 0.12960000336170197,
    "syPeak": 0.140,
}

FZ_VALUES = [2000.0, 3000.0, 4000.0, 5000.0, 6000.0, 7000.0]  # N

FONT_SIZE_LABEL = 24
FONT_SIZE_TICKS = 18
FONT_SIZE_LEGEND = 18
LINE_WIDTH = 2.0


def pacejka_forces(params, f_z, sx, sy, thermal_scaling=1.0):
    if f_z <= 0.0 or not np.isfinite(f_z) or not np.isfinite(sx) or not np.isfinite(sy):
        return 0.0, 0.0

    s_combined = np.sqrt(sx * sx + sy * sy)
    s_safe = np.maximum(s_combined, 1e-4)
    n_x = sx / s_safe
    n_y = sy / s_safe

    b_x = np.tan(np.pi / (2.0 * params["Cx"])) / max(params["sxPeak"], 1e-4)
    b_y = np.tan(np.pi / (2.0 * params["Cy"])) / max(params["syPeak"], 1e-4)

    f_z_clamped = np.clip(f_z, params["FzNom"] / 3.0, params["FzNom"] * 3.0)
    d_x_eff = params["Dx"] + params["Dx2"] * (f_z_clamped - params["FzNom"]) / params["FzNom"]
    d_y_eff = params["Dy"] + params["Dy2"] * (f_z_clamped - params["FzNom"]) / params["FzNom"]

    fx = thermal_scaling * f_z * n_x * d_x_eff * np.sin(params["Cx"] * np.arctan(b_x * s_combined))
    fy = thermal_scaling * f_z * n_y * d_y_eff * np.sin(params["Cy"] * np.arctan(b_y * s_combined))

    return fx, fy


def format_axes(ax):
    ax.tick_params(axis="both", which="major", labelsize=FONT_SIZE_TICKS)
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.5)


def plot_fx_slip_ratio():
    fig, ax = plt.subplots(figsize=(10, 8))
    slip_ratio = np.linspace(-0.5, 0.5, 801)

    for f_z in FZ_VALUES:
        fx_values = [pacejka_forces(PACEJKA_PARAMS, f_z, sx, 0.0)[0] / 1000.0 for sx in slip_ratio]
        ax.plot(slip_ratio, fx_values, linewidth=LINE_WIDTH, label=rf'$F_z={f_z/1000:.0f}\;\mathrm{{kN}}$')

    ax.set_xlabel(r'$\mathrm{Slip\ ratio}\;\lambda$', fontsize=FONT_SIZE_LABEL)
    ax.set_ylabel(r'$F_x\;\mathrm{(kN)}$', fontsize=FONT_SIZE_LABEL)
    ax.legend(fontsize=FONT_SIZE_LEGEND)
    format_axes(ax)
    fig.tight_layout()
    fig.savefig("vn_transformer_Fx_vs_slip_ratio.png", dpi=600)
    print("Saved vn_transformer_Fx_vs_slip_ratio.png")
    plt.close(fig)


def plot_fy_slip_angle():
    fig, ax = plt.subplots(figsize=(10, 8))
    slip_angle = np.linspace(-0.5, 0.5, 801)

    for f_z in FZ_VALUES:
        fy_values = [pacejka_forces(PACEJKA_PARAMS, f_z, 0.0, sy)[1] / 1000.0 for sy in slip_angle]
        ax.plot(slip_angle, fy_values, linewidth=LINE_WIDTH, label=rf'$F_z={f_z/1000:.0f}\;\mathrm{{kN}}$')

    ax.set_xlabel(r'$\mathrm{Slip\ angle}\;\alpha\;\mathrm{(rad)}$', fontsize=FONT_SIZE_LABEL)
    ax.set_ylabel(r'$F_y\;\mathrm{(kN)}$', fontsize=FONT_SIZE_LABEL)
    ax.legend(fontsize=FONT_SIZE_LEGEND)
    format_axes(ax)
    fig.tight_layout()
    fig.savefig("vn_transformer_Fy_vs_slip_angle.png", dpi=600)
    print("Saved vn_transformer_Fy_vs_slip_angle.png")
    plt.close(fig)


def main():
    plot_fx_slip_ratio()
    plot_fy_slip_angle()


if __name__ == "__main__":
    main()
