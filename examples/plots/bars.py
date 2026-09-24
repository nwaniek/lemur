"""Grouped bar chart with error bars and a legend."""
import numpy as np
import matplotlib.pyplot as plt


def figure():
    cats = ["vision", "audio", "text", "multimodal"]
    model = [0.91, 0.84, 0.88, 0.93]
    base = [0.83, 0.79, 0.81, 0.85]
    err = [0.02, 0.03, 0.02, 0.02]
    xs = np.arange(len(cats)); w = 0.38
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.bar(xs - w / 2, model, w, yerr=err, capsize=4, color="#2b6cb0", label="ours")
    ax.bar(xs + w / 2, base, w, yerr=err, capsize=4, color="#e08e0b", label="baseline")
    ax.set_xticks(xs); ax.set_xticklabels(cats)
    ax.set_ylabel("accuracy"); ax.set_ylim(0.7, 1.0)
    ax.legend(frameon=False, ncol=2, loc="upper center")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    return fig
