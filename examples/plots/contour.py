"""Filled contour of a scalar field, with overlaid lines and a colorbar."""
import numpy as np
import matplotlib.pyplot as plt


def figure():
    x = np.linspace(-3, 3, 300)
    y = np.linspace(-3, 3, 300)
    X, Y = np.meshgrid(x, y)
    Z = np.exp(-(X**2 + Y**2) / 3) * np.sin(2.2 * X) * np.cos(2.0 * Y)
    fig, ax = plt.subplots(figsize=(6.0, 4.6))
    cf = ax.contourf(X, Y, Z, levels=16, cmap="RdBu_r")
    ax.contour(X, Y, Z, levels=16, colors="k", linewidths=0.4, alpha=0.35)
    cb = fig.colorbar(cf, ax=ax, shrink=0.92)
    cb.set_label("field value")
    ax.set_xlabel("x"); ax.set_ylabel("y")
    ax.set_aspect("equal")
    fig.tight_layout()
    return fig
