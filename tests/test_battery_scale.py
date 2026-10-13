"""The battery layer with addon_scale="iqr" must give the same assignment when the black-box
cost F is replaced by aF + b (a > 0): the framework's scale-invariance guarantee.

    .venv/Scripts/python -m pytest tests/test_battery_scale.py -q
"""
import dataclasses
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evsim.battery import BIG, BatteryAddOn  # noqa: E402
from evsim.config import Config  # noqa: E402


class FixedBox:
    """Black box returning a given cost matrix."""
    def __init__(self, f, km):
        self.f, self.km = f, km

    def cost_matrix(self, cands, riders, t):
        return self.f.copy(), self.km


def make_layer(f, km, **over):
    cfg = dataclasses.replace(Config(), addon_scale="iqr", addon_feasible=False, addon_nudge=False, **over)
    layer = BatteryAddOn(cfg)
    layer.base = FixedBox(f, km)
    layer.last_scale = 1.0
    return layer


def test_assignment_unchanged_under_affine_cost():
    rng = np.random.default_rng(0)
    n, m = 12, 9
    km = rng.uniform(0.2, 5.0, (n, m))
    f = km + rng.normal(0, 0.5, (n, m))
    f[rng.random((n, m)) < 0.1] = BIG
    cands = [SimpleNamespace(v=SimpleNamespace(soc=s, id=i), soc=s) for i, s in enumerate(rng.uniform(0.1, 0.9, n))]
    riders = [SimpleNamespace(trip_km=k) for k in rng.uniform(2, 25, m)]
    ref = None
    for a, b in [(1.0, 0.0), (7.5, 0.0), (0.01, -30.0), (1000.0, 5e4)]:
        g = np.where(f < BIG / 2, a * f + b, BIG)
        layer = make_layer(g, km, addon_lambda=0.8)
        cost, _ = layer.cost_matrix(cands, riders, 0.0)
        pairs = sorted(zip(*linear_sum_assignment(cost)))
        ref = ref or pairs
        assert pairs == ref, f"assignment changed for a={a}, b={b}"
