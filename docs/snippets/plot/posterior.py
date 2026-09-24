"""The posterior of a coin's bias after more and more flips."""
from math import lgamma

import numpy as np
import matplotlib.pyplot as plt


def beta_pdf(x, a, b):
    return np.exp((a - 1) * np.log(x) + (b - 1) * np.log1p(-x) + lgamma(a + b) - lgamma(a) - lgamma(b))


def figure():
    theta = np.linspace(0.001, 0.999, 400)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for n, heads, color in [(4, 3, "#9db4c0"), (20, 14, "#5c8fa3"), (100, 71, "#2e5e6e")]:
        ax.plot(theta, beta_pdf(theta, 1 + heads, 1 + n - heads), color=color, lw=2.5,
                label=f"{n} flips")
    ax.set_xlabel(r"bias $\theta$")
    ax.set_ylabel(r"$p(\theta \mid x)$")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    return fig
