"""Small camera helper shared by the scenes."""
import numpy as np


def edge_on_azim(view_elev_deg, n, near_azim_deg):
    """The camera azimuth (degrees), closest to ``near_azim_deg``, that sees the
    plane with normal ``n`` exactly edge-on from elevation ``view_elev_deg``."""
    e = np.radians(view_elev_deg)
    a = np.radians(np.linspace(near_azim_deg - 180, near_azim_deg + 180, 7201))
    toward = np.stack([-np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.full_like(a, np.sin(e))], 1)
    s = np.abs(toward @ n)
    zero = np.where(s < s.min() + 1e-3)[0]
    return float(np.degrees(a[min(zero, key=lambda i: abs(a[i] - np.radians(near_azim_deg)))]))
