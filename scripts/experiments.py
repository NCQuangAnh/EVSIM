"""Experiment catalogue for scripts/run_jobs.py (local or Kaggle).

An experiment is a set of arms run on the same seeds. Every arm names the arm it is paired
with (its own black box), so one experiment can hold several black boxes.

Protocol defaults (docs/protocol.md): common random numbers on, drivers charge before driving
home, development seeds 300+, evaluation seeds 1000+ (evaluation experiments are added only
once the module is locked).
"""
SCALES = {
    "small": {"n_vehicles": 1000, "daily_requests": 23333},
    "full": {},
}
PROTOCOL = {"crn": True, "charge_before_home": True}
DEV_SEEDS = list(range(300, 310))

OFF = {"addon_feasible": False, "addon_reject": False, "addon_nudge": False}
V1 = {}                                            # module v1: (a)(b)(c), lambda 1 in black-box units
IQR = {"addon_scale": "iqr", "addon_lambda": 0.5}  # (b) in IQR units of the black-box cost
B1 = ("black box B1", "gsm_baseline", {}, None)


def arm(name, over, ref="black box B1", policy="battery_addon"):
    return (name, policy, over, ref)


EXPERIMENTS = {
    # does the gain from charge nudges survive drivers who ignore them?
    "nudge_compliance": dict(scale="small", seeds=DEV_SEEDS, arms=[
        B1,
        *[arm(f"v1 full, nudge followed p={p}", {"nudge_accept_p": p}) for p in (1.0, 0.7, 0.5, 0.3, 0.0)],
        arm("(c) only, p=0.5", {**OFF, "addon_nudge": True, "nudge_accept_p": 0.5}),
    ]),
    # safety reserve of the feasibility mask (a)
    "reserve": dict(scale="small", seeds=DEV_SEEDS, arms=[
        B1,
        *[arm(f"(a) only, reserve {r:.0%}", {**OFF, "addon_feasible": True, "soc_reserve": r}) for r in (0.0, 0.03, 0.08)],
        *[arm(f"v1 full, reserve {r:.0%}", {"soc_reserve": r}) for r in (0.0, 0.03, 0.08)],
    ]),
    # decline-risk term (b) in IQR units: size, and alone
    "scale_lambda": dict(scale="small", seeds=DEV_SEEDS, arms=[
        B1,
        *[arm(f"full, IQR lambda {lam}", {"addon_scale": "iqr", "addon_lambda": lam}) for lam in (0.25, 0.5, 1.0, 2.0)],
        arm("(b) only, IQR lambda 1", {**OFF, "addon_reject": True, "addon_scale": "iqr", "addon_lambda": 1.0}),
        arm("(b) only, IQR lambda 4", {**OFF, "addon_reject": True, "addon_scale": "iqr", "addon_lambda": 4.0}),
    ]),
    # bonus sizes (0.5 is run locally in scripts/dev_ablation.py --group bonus)
    "bonus_size": dict(scale="small", seeds=DEV_SEEDS, arms=[
        B1,
        *[arm(f"full IQR + station bonus {b}", {**IQR, "addon_station_bonus": b}) for b in (0.25, 1.0, 2.0)],
        *[arm(f"full IQR + pre-peak bonus {b}", {**IQR, "addon_prepeak_bonus": b}) for b in (0.25, 1.0, 2.0)],
    ]),
    # the same module on the black boxes that exist today (B0, B6 come with phase 2)
    "blackbox_dev": dict(scale="small", seeds=DEV_SEEDS, arms=[
        B1,
        arm("B1 + v1 full", V1),
        arm("B1 + full IQR", IQR),
        ("black box B2-F", "gsm_fwd", {}, None),
        arm("B2-F + full IQR", {**IQR, "addon_base": "gsm_fwd"}, ref="black box B2-F"),
        ("black box B2-R", "gsm_repo", {}, None),
        arm("B2-R + full IQR", {**IQR, "addon_base": "gsm_repo"}, ref="black box B2-R"),
        ("black box B2", "gsm_fwd_repo", {}, None),
        arm("B2 + full IQR", {**IQR, "addon_base": "gsm_fwd_repo"}, ref="black box B2"),
        ("black box B4c", "b4_didi", {"didi_cancel_aware": True}, None),
        arm("B4c + full IQR", {**IQR, "addon_base": "b4_didi", "didi_cancel_aware": True}, ref="black box B4c"),
        arm("B4c + v1 full", {"addon_base": "b4_didi", "didi_cancel_aware": True}, ref="black box B4c"),
    ]),
}
# Hard driver behaviour (batch dev2): does the matching side ((a), (b), station bonus) earn its
# place when drivers do not manage their battery themselves, or ignore most nudges?
BEHAVIOURS = {
    "no_battery_declines": {"driver_soc_decline": False},           # drivers never refuse a ride for battery
    "late_chargers": {"soc_threshold_min": 0.03, "soc_threshold_max": 0.12},
    "low_compliance": {"nudge_accept_p": 0.3},                       # 30 % of nudges followed
    "no_declines_low_compliance": {"driver_soc_decline": False, "nudge_accept_p": 0.3},
}
C_ONLY = {**OFF, "addon_nudge": True}
for _name, _extra in BEHAVIOURS.items():
    EXPERIMENTS[f"behaviour_{_name}"] = dict(scale="small", seeds=DEV_SEEDS, extra=_extra, arms=[
        B1,
        arm("(c) only", C_ONLY),
        arm("(a)(c)", {**C_ONLY, "addon_feasible": True}),
        arm("(a)(b)(c) IQR", IQR),
        arm("(a)(b)(c) IQR + station bonus", {**IQR, "addon_station_bonus": 0.5}),
        arm("(a) only", {**OFF, "addon_feasible": True}),
        arm("station bonus only", {**OFF, **IQR, "addon_station_bonus": 0.5}),
    ])

# Value of knowing each driver's habits (batch dev3, docs/driver_model_design.md): legacy rules vs
# the population model (pooled) vs each driver's true parameters (oracle = what a perfect behaviour
# tracker would know). oracle - pooled is the ceiling of the tracker's value.
LEGACY_MATCH = {**IQR, "addon_station_bonus": 0.5}
SMART_C = {**C_ONLY, "nudge_mode": "smart"}
ORACLE_WORLDS = {"base": {}, "no_battery_declines": BEHAVIOURS["no_battery_declines"],
                 "late_chargers": BEHAVIOURS["late_chargers"]}
for _name, _extra in ORACLE_WORLDS.items():
    EXPERIMENTS[f"oracle_{_name}"] = dict(scale="small", seeds=DEV_SEEDS, extra=_extra, arms=[
        B1,
        arm("(c) time-of-day only", C_ONLY),
        arm("legacy (a)(b)(d) + time-of-day (c)", LEGACY_MATCH),
        arm("pooled (a)(b)(d) + time-of-day (c)", {**LEGACY_MATCH, "driver_model": "pooled"}),
        arm("oracle (a)(b)(d) + time-of-day (c)", {**LEGACY_MATCH, "driver_model": "oracle"}),
        arm("smart (c) only, pooled", {**SMART_C, "driver_model": "pooled"}),
        arm("smart (c) only, oracle", {**SMART_C, "driver_model": "oracle"}),
        arm("pooled (a)(b)(d) + smart (c)", {**LEGACY_MATCH, "driver_model": "pooled", "nudge_mode": "smart"}),
        arm("oracle (a)(b)(d) + smart (c)", {**LEGACY_MATCH, "driver_model": "oracle", "nudge_mode": "smart"}),
    ])

# Coupling the safety mask (a) to charging (batch dev4). In dev2, (a) alone hurt late chargers
# (-0.09 pt): cars kept idle at low SOC above their own threshold. Fixes: mask-triggered nudges
# (SOC too low for a typical trip, sized by mask_nudge_km) and the soft low-margin penalty (a').
A_ONLY = {**OFF, "addon_feasible": True}
MASK_WORLDS = {"base": {}, "late_chargers": BEHAVIOURS["late_chargers"],
               "no_battery_declines": BEHAVIOURS["no_battery_declines"]}
for _name, _extra in MASK_WORLDS.items():
    EXPERIMENTS[f"mask_{_name}"] = dict(scale="small", seeds=DEV_SEEDS, extra=_extra, arms=[
        B1,
        arm("(a) only", A_ONLY),
        *[arm(f"(a) + mask nudge {km} km", {**A_ONLY, "addon_mask_nudge": True, "mask_nudge_km": km})
          for km in (12.0, 20.0, 30.0)],
        arm("(a') soft margin only", {**OFF, "addon_soft_margin": 0.5, "addon_scale": "iqr"}),
        arm("(a)(a') hard + soft", {**A_ONLY, "addon_soft_margin": 0.5, "addon_scale": "iqr"}),
        arm("(c) only", C_ONLY),
        arm("(a)(c)", {**C_ONLY, "addon_feasible": True}),
        arm("(a)(a')(c) + mask nudge 20 km", {**C_ONLY, "addon_feasible": True, "addon_mask_nudge": True,
                                               "mask_nudge_km": 20.0, "addon_soft_margin": 0.5,
                                               "addon_scale": "iqr"}),
    ])

# T1 (batch dev5): heterogeneous, noisy drivers (driver_hetero: per-decision threshold noise,
# higher threshold near the end of the shift, personal decline margin/sharpness, unplug noise,
# per-driver nudge compliance ~ Beta(mean 0.6)). Re-runs the T0 ceiling (oracle vs pooled) with
# the module v2 candidate: (a) + mask nudge 30 km, (b) IQR lambda 0.5, (c); nudges time-of-day /
# smart / hybrid.
V2 = {**IQR, "addon_mask_nudge": True, "mask_nudge_km": 30.0}
HETERO_WORLDS = {"hetero": {"driver_hetero": True},
                 "hetero_late": {"driver_hetero": True, **BEHAVIOURS["late_chargers"]}}
for _name, _extra in HETERO_WORLDS.items():
    EXPERIMENTS[f"t1_{_name}"] = dict(scale="small", seeds=DEV_SEEDS, extra=_extra, arms=[
        B1,
        arm("(c) time-of-day only", C_ONLY),
        arm("smart (c) only, pooled", {**SMART_C, "driver_model": "pooled"}),
        arm("smart (c) only, oracle", {**SMART_C, "driver_model": "oracle"}),
        arm("v2 time-of-day, legacy", V2),
        arm("v2 time-of-day, pooled", {**V2, "driver_model": "pooled"}),
        arm("v2 time-of-day, oracle", {**V2, "driver_model": "oracle"}),
        arm("v2 smart, pooled", {**V2, "driver_model": "pooled", "nudge_mode": "smart"}),
        arm("v2 smart, oracle", {**V2, "driver_model": "oracle", "nudge_mode": "smart"}),
        arm("v2 hybrid, pooled", {**V2, "driver_model": "pooled", "nudge_mode": "hybrid"}),
        arm("v2 hybrid, oracle", {**V2, "driver_model": "oracle", "nudge_mode": "hybrid"}),
    ])

# Phase 2 (batch dev6), heterogeneous drivers (the main world from now on):
#  bb7     module v2 on all 7 black boxes (goal B: no black box worse; goal C: average gain)
#  levels  capability ablation: the same module limited to interface levels L0..L3
HET = {"driver_hetero": True}
BLACK_BOXES = {"B0": ("b0_greedy", {}), "B1": ("gsm_baseline", {}), "B2-F": ("gsm_fwd", {}),
               "B2-R": ("gsm_repo", {}), "B2": ("gsm_fwd_repo", {}), "B6": ("b6_value", {}),
               "B4c": ("b4_didi", {"didi_cancel_aware": True})}
_bb_arms = []
for _k, (_pol, _over) in BLACK_BOXES.items():
    _bb_arms += [(f"black box {_k}", _pol, _over, None),
                 arm(f"{_k} + v2", {**V2, **_over, "addon_base": _pol}, ref=f"black box {_k}")]
EXPERIMENTS["bb7"] = dict(scale="small", seeds=DEV_SEEDS, extra=HET, arms=_bb_arms)
_lv_arms = []
for _k, _levels in {"B1": (0, 1), "B2": (0, 1, 2), "B4c": (0, 1, 2, 3)}.items():
    _pol, _over = BLACK_BOXES[_k]
    _lv_arms.append((f"black box {_k}", _pol, _over, None))
    for _lv in _levels:
        _extra_lv = {"nudge_mode": "value"} if _lv == 3 else {}
        _lv_arms.append(arm(f"{_k} + v2 at L{_lv}", {**V2, **_over, "addon_base": _pol, "addon_level": _lv, **_extra_lv},
                            ref=f"black box {_k}"))
EXPERIMENTS["levels"] = dict(scale="small", seeds=DEV_SEEDS, extra=HET, arms=_lv_arms)

# dev7: the main lever (c), on B1, heterogeneous drivers. Every arm is module v2 with one change.
#  schedule  pre-peak level 40/50/60 % x pre-peak window 1 / 1.5 / 2 h; off-peak level 20 / 40 %
#  target    supply-target nudges before the peaks (share x SOC target, 2 h lookahead), congestion-aware
#  home      end-of-shift nudge to charge at home overnight (acceptance 30 / 60 %), with and without (c)
_sched = [arm("v2 (default schedule)", V2)]
for _lvl in (0.4, 0.5, 0.6):
    for _L in (1.0, 1.5, 2.0):
        _sched.append(arm(f"v2 pre-peak {_lvl:.0%} for {_L:g} h",
                          {**V2, "nudge_soc_prepeak": _lvl, "nudge_prepeak_hours": ((7.0 - _L, 7.0), (17.0 - _L, 17.0))}))
_sched += [arm(f"v2 off-peak {_lvl:.0%}", {**V2, "nudge_soc": _lvl}) for _lvl in (0.2, 0.4)]
_target = [arm(f"v2 target {_sh:.0%} at SOC {_soc:.0%}", {**V2, "nudge_mode": "target", "target_share": _sh, "target_soc": _soc})
           for _sh in (0.8, 0.9) for _soc in (0.5, 0.6)]
_home = [arm(f"v2 + home nudge {_acc:.0%}", {**V2, "addon_home_nudge": True, "home_nudge_accept": _acc}) for _acc in (0.3, 0.6)]
_home.append(arm("home nudge 60 % only", {**OFF, "addon_home_nudge": True, "home_nudge_accept": 0.6}))
EXPERIMENTS["nudge_design"] = dict(scale="small", seeds=DEV_SEEDS, extra=HET, arms=[B1, *_sched, *_target, *_home])

# dev8: refine the nudge schedule found in dev7 (higher pre-peak levels, longer windows, supply
# targets at 70 %, combinations with home nudges and a 40 % off-peak level), on three black boxes
# of different structure (B0 greedy, B1 GSM, B4c DiDi) so the schedule is not tuned to one of them.
def _pp(level, hours):
    return {"nudge_soc_prepeak": level, "nudge_prepeak_hours": ((7.0 - hours, 7.0), (17.0 - hours, 17.0))}
SCHEDULES = {
    "v2 default": {},
    "pre-peak 60% 2h": _pp(0.6, 2.0),
    "pre-peak 70% 2h": _pp(0.7, 2.0),
    "pre-peak 80% 2h": _pp(0.8, 2.0),
    "pre-peak 70% 2.5h": _pp(0.7, 2.5),
    "target 80% at 60%": {"nudge_mode": "target", "target_share": 0.8, "target_soc": 0.6},
    "target 80% at 70%": {"nudge_mode": "target", "target_share": 0.8, "target_soc": 0.7},
    "pre-peak 70% 2h + off-peak 40% + home 60%": {**_pp(0.7, 2.0), "nudge_soc": 0.4, "addon_home_nudge": True,
                                                  "home_nudge_accept": 0.6},
    "target 80% at 70% + off-peak 40% + home 60%": {"nudge_mode": "target", "target_share": 0.8, "target_soc": 0.7,
                                                    "nudge_soc": 0.4, "addon_home_nudge": True, "home_nudge_accept": 0.6},
}
for _k in ("B0", "B1", "B4c"):
    _pol, _over = BLACK_BOXES[_k]
    EXPERIMENTS[f"schedule_{_k}"] = dict(scale="small", seeds=DEV_SEEDS, extra=HET, arms=[
        (f"black box {_k}", _pol, _over, None),
        *[arm(f"{_k} + {_name}", {**V2, **_over, "addon_base": _pol, **_sch}, ref=f"black box {_k}")
          for _name, _sch in SCHEDULES.items()],
    ])

# ---------------- LOCKED for evaluation (2026-10-11, after dev8; do not tune on eval seeds) ----------------
# Module v2.1 = v2 [(a) + mask nudge 30 km, (b) IQR lambda 0.5 legacy curve, (c)] with the pre-peak
# nudge level 70 % over 2.5 h before each peak (dev8 winner without the home-charging assumption).
# Variant "+ home": also asks drivers ending a shift below 60 % to charge at home (60 % of those
# who would not have done so comply - an assumption, reported separately).
EVAL_SEEDS = list(range(1000, 1020))
V21 = {**V2, **_pp(0.7, 2.5)}
V21_HOME = {**V21, "addon_home_nudge": True, "home_nudge_accept": 0.6}
_eval_arms = []
for _k, (_pol, _over) in BLACK_BOXES.items():
    _eval_arms += [(f"black box {_k}", _pol, _over, None),
                   arm(f"{_k} + v2.1", {**V21, **_over, "addon_base": _pol}, ref=f"black box {_k}")]
for _k in ("B1", "B4c"):
    _pol, _over = BLACK_BOXES[_k]
    _eval_arms.append(arm(f"{_k} + v2.1 + home", {**V21_HOME, **_over, "addon_base": _pol}, ref=f"black box {_k}"))
EXPERIMENTS["eval_main"] = dict(scale="full", seeds=EVAL_SEEDS, extra=HET, arms=_eval_arms)

# OOD screening (batch ood1, 1,000 cars, evaluation seeds 1000-1009, locked v2.1, no tuning):
# conditions the module was not developed on. Worst one is repeated at full scale afterwards.
OOD = {
    "demand_minus20": {"daily_requests": int(23333 * 0.8)},
    "demand_plus20": {"daily_requests": int(23333 * 1.2)},
    "ports_60pct": {"port_scale": 0.6},
    "harsh": {"kwh_per_km": 0.20, "soc_info": "noise", "nudge_accept_mean": 0.4},   # hungrier cars, noisy SOC, fewer follow nudges
}
for _name, _cond in OOD.items():
    _arms = []
    for _k, (_pol, _over) in BLACK_BOXES.items():
        _arms += [(f"black box {_k}", _pol, _over, None),
                  arm(f"{_k} + v2.1", {**V21, **_over, "addon_base": _pol}, ref=f"black box {_k}")]
    EXPERIMENTS[f"ood_{_name}"] = dict(scale="small", seeds=EVAL_SEEDS[:10], extra={**HET, **_cond}, arms=_arms)

# Worst OOD condition in ood1 (demand +20 %: B0 profit LCB -2.6k, fails the 2,000 VND margin at
# 1,000 cars) repeated at full scale with the evaluation seeds (batch ood2), locked v2.1 unchanged.
_arms = []
for _k, (_pol, _over) in BLACK_BOXES.items():
    _arms += [(f"black box {_k}", _pol, _over, None),
              arm(f"{_k} + v2.1", {**V21, **_over, "addon_base": _pol}, ref=f"black box {_k}")]
EXPERIMENTS["ood_full_demand_plus20"] = dict(scale="full", seeds=EVAL_SEEDS, extra={**HET, "daily_requests": int(118533 * 1.2)},
                                             arms=_arms)

# v2.2 development (batch dev9, dev seeds 300-309, 1,000 cars): supply-aware gate on the pre-peak
# nudges, in the base world and with demand +20 % (where v2.1 failed for B0), on B0, B1, B6.
GATES = {"v2.1": {}, "v2.1 + idle gate 15%": {"nudge_gate": "idle_share", "gate_idle_share": 0.15},
         "v2.1 + idle gate 25%": {"nudge_gate": "idle_share", "gate_idle_share": 0.25},
         "v2.1 + surplus gate 0.5": {"nudge_gate": "surplus", "gate_surplus_frac": 0.5},
         "v2.1 + surplus gate 1.0": {"nudge_gate": "surplus", "gate_surplus_frac": 1.0}}
for _world, _wx in {"base": {}, "demand_plus20": {"daily_requests": int(23333 * 1.2)}}.items():
    _arms = []
    for _k in ("B0", "B1", "B6"):
        _pol, _over = BLACK_BOXES[_k]
        _arms.append((f"black box {_k}", _pol, _over, None))
        _arms += [arm(f"{_k} + {_g}", {**V21, **_over, "addon_base": _pol, **_gx}, ref=f"black box {_k}")
                  for _g, _gx in GATES.items()]
    EXPERIMENTS[f"gate_{_world}"] = dict(scale="small", seeds=DEV_SEEDS, extra={**HET, **_wx}, arms=_arms)

# ---------------- LOCKED v2.2 (2026-10-12, after dev9) ----------------
# v2.2 = v2.1 + supply-aware gate on the raised pre-peak nudges: at most 0.5 x (idle cars - waiting
# riders) extra cars per nudge round, lowest SOC first. Chosen on dev seeds 300-309 (dev9): equal or
# better than v2.1 in the base world, clearly better with demand +20 %. Evaluated on FRESH seeds
# 2000-2019 (1000-1019 were seen in eval1 / ood1), full scale, main world and demand +20 %.
EVAL2_SEEDS = list(range(2000, 2020))
V22 = {**V21, "nudge_gate": "surplus", "gate_surplus_frac": 0.5}
for _name, _wx, _seeds in (("eval2_main", {}, EVAL2_SEEDS),
                           ("eval2_demand_plus20", {"daily_requests": int(118533 * 1.2)}, EVAL2_SEEDS[:10])):
    _arms = []
    for _k, (_pol, _over) in BLACK_BOXES.items():
        _arms += [(f"black box {_k}", _pol, _over, None),
                  arm(f"{_k} + v2.2", {**V22, **_over, "addon_base": _pol}, ref=f"black box {_k}")]
    EXPERIMENTS[_name] = dict(scale="full", seeds=_seeds, extra={**HET, **_wx}, arms=_arms)

# Ceiling of any battery technique (dev seeds, heterogeneous drivers, B1): how much better B1 gets
# when parts of the battery problem are removed by magic. gain(v2.1) / gain(no battery) = share of
# the battery-caused loss that the framework already recovers.
FAST = {"dc_kw": 1e5, "taper_soc": 1.0, "taper_kw": 1e5, "vehicle_max_dc_kw": 1e5, "vehicle_max_ac_kw": 1e5,
        "dc_curve_factor": 1.0}
EXPERIMENTS["ceiling"] = dict(scale="small", seeds=DEV_SEEDS[:5], extra=HET, arms=[
    B1,
    arm("B1 + v2.1", V21),
    arm("B1 + v2.2", V22),
    ("magic: no battery (zero consumption)", "gsm_baseline", {"kwh_per_km": 1e-6}, "black box B1"),
    ("magic: instant charging, no queues", "gsm_baseline", {**FAST, "port_scale": 20.0}, "black box B1"),
    ("magic: no battery declines", "gsm_baseline", {"driver_soc_decline": False}, "black box B1"),
    ("magic: instant charging + v2.1", "battery_addon", {**V21, **FAST, "port_scale": 20.0}, "black box B1"),
])

# Does the "skip cars whose shift ends within 1 h" nudge rule need the exact shift end? (dev seeds, B1,
# heterogeneous drivers): exact (registered shifts) vs an estimate off by N(0, 60 / 120 min) vs no rule.
EXPERIMENTS["shift_info"] = dict(scale="small", seeds=DEV_SEEDS[:10], extra=HET, arms=[
    B1,
    arm("B1 + v2.1, exact shift end", V21),
    arm("B1 + v2.1, shift end ± 60 min", {**V21, "shift_end_info": "noisy", "shift_end_noise_min": 60.0}),
    arm("B1 + v2.1, shift end ± 120 min", {**V21, "shift_end_info": "noisy", "shift_end_noise_min": 120.0}),
    arm("B1 + v2.1, no shift-end rule", {**V21, "shift_end_info": "none"}),
])

# experiments launched together in one Kaggle batch
BATCHES = {
    "dev1": ["nudge_compliance", "reserve", "scale_lambda", "bonus_size", "blackbox_dev"],
    "dev2": [f"behaviour_{n}" for n in BEHAVIOURS],
    "dev3": [f"oracle_{n}" for n in ORACLE_WORLDS],
}
BATCHES["dev4"] = [f"mask_{n}" for n in MASK_WORLDS]
BATCHES["dev23"] = BATCHES["dev2"] + BATCHES["dev3"]   # both in one go
BATCHES["dev34"] = BATCHES["dev3"] + BATCHES["dev4"]
BATCHES["dev5"] = [f"t1_{n}" for n in HETERO_WORLDS]
BATCHES["dev6"] = ["bb7", "levels"]
BATCHES["dev7"] = ["nudge_design"]
BATCHES["dev67"] = BATCHES["dev6"] + BATCHES["dev7"]
BATCHES["dev8"] = ["schedule_B0", "schedule_B1", "schedule_B4c"]
BATCHES["eval1"] = ["eval_main"]
BATCHES["ood1"] = [f"ood_{n}" for n in OOD]
BATCHES["ood2"] = ["ood_full_demand_plus20"]
BATCHES["dev9"] = ["gate_base", "gate_demand_plus20"]
BATCHES["eval2"] = ["eval2_main", "eval2_demand_plus20"]
