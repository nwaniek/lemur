"""Violin plot: full distributions per group, with the means marked."""
import numpy as np
import matplotlib.pyplot as plt


def figure():
    rng = np.random.default_rng(0)
    specs = [(0.0, 1.0), (1.2, 1.4), (2.0, 0.7), (1.5, 1.1)]
    data = [rng.normal(mu, sd, 300) for mu, sd in specs]
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    parts = ax.violinplot(data, showmeans=True, showextrema=False)
    for body in parts["bodies"]:
        body.set_facecolor("#2b6cb0"); body.set_alpha(0.55)
    parts["cmeans"].set_color("#c0392b")
    ax.set_xticks([1, 2, 3, 4]); ax.set_xticklabels(["control", "A", "B", "C"])
    ax.set_ylabel("response"); ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    return fig
