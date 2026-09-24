"""Scatter + least-squares fit, with a legend and an arrow annotation."""
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(3)
x = np.linspace(0, 10, 40)
y = 0.8 * x + 1.5 + rng.normal(0, 1.2, x.size)
y[37] -= 4.0                                   # plant a clear outlier
m, b = np.polyfit(np.delete(x, 37), np.delete(y, 37), 1)


def figure():
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.scatter(x, y, s=40, color="#2b6cb0", alpha=0.85, label="observations")
    ax.plot(x, m * x + b, color="#c0392b", lw=2.5, label=f"fit:  y = {m:.2f}x + {b:.2f}")
    ax.annotate("outlier", xy=(x[37], y[37]), xytext=(x[37] - 3.2, y[37] - 1.6),
                arrowprops=dict(arrowstyle="->", color="#333", lw=1.5), fontsize=12)
    ax.set_xlabel("time (s)"); ax.set_ylabel("signal (mV)")
    ax.legend(loc="upper left", frameon=False)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig
