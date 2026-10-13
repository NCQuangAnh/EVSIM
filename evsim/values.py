"""Spatio-temporal state values V(cell, time slot) for value-based dispatch (B4), following
Xu et al., "Large-Scale Order Dispatch in On-Demand Ride-Hailing Platforms: A Learning and
Planning Approach", KDD 2018 (papers/DiDi): square cells (~1.1 km here), 10-minute slots,
gamma = 0.9, one driver-day per episode, policy evaluation by dynamic programming backwards
over the slots of the day (Algorithm 1)."""
from pathlib import Path

import numpy as np

from .demand import AREA

CELL_DEG = 0.01
SLOT_S = 600
SLOTS = 24 * 3600 // SLOT_S  # end of the day = end of the episode, V = 0 beyond it


class Grid:
    def __init__(self):
        self.lat0, lat1, self.lon0, lon1 = AREA[0], AREA[1], AREA[2], AREA[3]
        self.rows = int(np.ceil((lat1 - self.lat0) / CELL_DEG))
        self.cols = int(np.ceil((lon1 - self.lon0) / CELL_DEG))
        self.n = self.rows * self.cols

    def cell(self, lat, lon):
        r = np.clip(np.floor((np.asarray(lat) - self.lat0) / CELL_DEG).astype(int), 0, self.rows - 1)
        c = np.clip(np.floor((np.asarray(lon) - self.lon0) / CELL_DEG).astype(int), 0, self.cols - 1)
        return r * self.cols + c


def slot(t_s):
    """Slot of the day (0..143)."""
    return (np.floor(np.asarray(t_s) / SLOT_S).astype(int)) % SLOTS


def slot_after(t_start_s, t_end_s):
    """Slot of t_end counted from the start of t_start's day; >= SLOTS means past the episode end."""
    day0 = np.floor(np.asarray(t_start_s) / 86400) * 86400
    return np.floor((np.asarray(t_end_s) - day0) / SLOT_S).astype(int)


def spread_reward(reward, dt_slots, gamma):
    """Eq. (1): a price R paid evenly over T slots, discounted: sum_{t<T} gamma^t R / T
    (continuous form for non-integer T)."""
    dt = np.maximum(np.asarray(dt_slots, dtype=float), 1e-6)
    return reward * (1 - gamma ** dt) / ((1 - gamma) * dt)


def lookup(V, cells, slots_abs):
    """V(s'), zero once the episode (the day) has ended."""
    slots_abs = np.asarray(slots_abs)
    inside = slots_abs < SLOTS
    out = np.zeros(np.broadcast(cells, slots_abs).shape)
    c, s = np.broadcast_arrays(cells, np.minimum(slots_abs, SLOTS - 1))
    out[...] = np.where(inside, V[c, s], 0.0)
    return out


def evaluate(transitions, grid, gamma):
    """Algorithm 1 (policy evaluation by DP): for t = T-1 .. 0, V(s) is the average over the
    transitions starting in s of gamma^dt * V(s') + R_gamma. Unvisited states keep V = 0.
    transitions: dict of arrays s_cell, s_slot (0..143), e_cell, e_slot (slots after the start
    of the day of s, may exceed 143), dt (slots), r (R_gamma)."""
    tr = transitions
    V = np.zeros((grid.n, SLOTS))
    N = np.zeros((grid.n, SLOTS))
    for t in range(SLOTS - 1, -1, -1):
        m = tr["s_slot"] == t
        if not m.any():
            continue
        # two passes so transitions ending inside the same slot see that slot's estimate
        for _ in range(2):
            target = gamma ** tr["dt"][m] * lookup(V, tr["e_cell"][m], tr["e_slot"][m]) + tr["r"][m]
            cnt = np.bincount(tr["s_cell"][m], minlength=grid.n)
            tot = np.bincount(tr["s_cell"][m], weights=target, minlength=grid.n)
            seen = cnt > 0
            V[seen, t] = tot[seen] / cnt[seen]
        N[:, t] = cnt
    return V, N


def load(path):
    z = np.load(Path(path))
    return z["V"], float(z["gamma"])
