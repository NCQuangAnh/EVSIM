"""Ocean Park 1 demo: a black box vs the same black box + battery layer v2.1, same seed
(docs/OCP1_DATA.md). Black boxes: B1 (GSM-style, default), B0 greedy, B6 immediate value,
B2 forward + repositioning. Scenarios: normal, and harsh (stress: hungrier cars, noisy SOC,
fewer drivers follow nudges - the OOD condition with the largest gain at Hanoi scale).

    # paired statistics over seeds for every scenario x black box (also picks the demo seeds)
    .venv/Scripts/python -W ignore scripts/ocp1_demo.py stats --jobs 4
    # replay files for the web player, day 2 of each run, using the representative seeds
    .venv/Scripts/python -W ignore scripts/ocp1_demo.py export

The demo seed of each combination is the one closest to the median gains in service, peak
service and profit at once, so the replay shows a typical day, not the best one.
"""
import argparse
import dataclasses
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from evsim import ocp1  # noqa: E402
from evsim.battery import POLICIES  # noqa: E402
from evsim.config import SCENARIOS, Config  # noqa: E402
from evsim.metrics import summarize  # noqa: E402
from evsim.simulator import Simulator  # noqa: E402

V21 = {"addon_scale": "iqr", "addon_lambda": 0.5, "addon_mask_nudge": True, "mask_nudge_km": 30.0,
       "nudge_soc_prepeak": 0.7, "nudge_prepeak_hours": ((4.5, 7.0), (14.5, 17.0))}
BLACK_BOXES = {"b1": ("gsm_baseline", "B1 · kiểu GSM: khoảng cách + rủi ro huỷ"),
               "b0": ("b0_greedy", "B0 · greedy: xe gần nhất"),
               "b6": ("b6_value", "B6 · giá trị kỳ vọng của chuyến"),
               "b2": ("gsm_fwd_repo", "B2 · B1 + forward dispatch + repositioning")}
SCENES = {"normal": ({}, "Bình thường"),
          "harsh": ({"kwh_per_km": 0.20, "soc_info": "noise", "nudge_accept_mean": 0.4}, "Khắc nghiệt (stress)")}
KEYS = ["service_level", "service_level_peak", "wait_min_mean", "wait_min_p90", "ride_reject_soc_share",
        "peak_share_charging", "charge_queue_min_mean", "strandings_per_day", "energy_cost_adj_vnd_day",
        "profit_adj_per_vehicle_day_vnd", "charge_sessions_per_day", "charge_nudges_per_day"]
PCT = ("service_level", "service_level_peak", "ride_reject_soc_share", "peak_share_charging")
OUT = ROOT / "outputs" / "ocp1"
WEB = ROOT / "web" / "public" / "data"
DAY = 86400.0


def make(scene, bb, arm, seed, log=False):
    pol = BLACK_BOXES[bb][0]
    over = {} if arm == "base" else {**V21, "addon_base": pol}
    cfg = dataclasses.replace(Config(), seed=seed, **{**SCENARIOS["ocp1_demo"], **SCENES[scene][0], **over,
                                                      "log_moves": log})
    sim = Simulator(cfg, POLICIES[pol if arm == "base" else "battery_addon"](cfg))
    sim.run()
    return sim


def one(job):
    scene, bb, arm, seed = job
    m = summarize(make(scene, bb, arm, seed))[0]
    return {"scene": scene, "bb": bb, "arm": arm, "seed": seed, **{k: float(m[k]) for k in KEYS}}


def cmd_stats(a):
    seeds = list(range(a.seeds[0], a.seeds[1] + 1))
    jobs = [(sc, bb, arm, s) for sc in a.scenes for bb in a.bbs for s in seeds for arm in ("base", "v21")]
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "ocp1_stats_runs_all.csv"
    old = pd.read_csv(f) if f.exists() else pd.DataFrame(columns=["scene", "bb", "arm", "seed"])
    done = set(zip(old.scene, old.bb, old.arm, old.seed))
    todo = [j for j in jobs if j not in done]
    rows = old.to_dict("records")
    print(f"{len(todo)} runs to do", flush=True)
    with ProcessPoolExecutor(a.jobs) as ex:
        for k, r in enumerate(ex.map(one, todo), 1):
            rows.append(r)
            pd.DataFrame(rows).to_csv(f, index=False)          # resumable
            if k % 20 == 0:
                print(f"{k}/{len(todo)}", flush=True)
    df = pd.DataFrame(rows)
    md, manifest = [], []
    for sc in a.scenes:
        for bb in a.bbs:
            sel = (df.scene == sc) & (df.bb == bb)
            b = df[sel & (df.arm == "base")].set_index("seed")
            v = df[sel & (df.arm == "v21")].set_index("seed")
            ok = b.index.intersection(v.index)
            b, v = b.loc[ok], v.loc[ok]
            table, summary = [], {}
            for k in KEYS:
                scale = 100 if k in PCT else 1
                d = (v[k] - b[k]) * scale
                h = student_t.ppf(0.975, len(d) - 1) * d.std(ddof=1) / np.sqrt(len(d))
                table.append({"metric": k, "black box": round(b[k].mean() * scale, 3),
                              "+ v2.1": round(v[k].mean() * scale, 3), "diff": round(d.mean(), 3),
                              "95% CI ±": round(h, 3), "share of seeds > 0": f"{(d > 0).mean():.0%}"})
                summary[k] = {"diff": float(d.mean()), "ci": float(h), "pos": float((d > 0).mean())}
            g = pd.DataFrame({k: v[k] - b[k] for k in ("service_level", "service_level_peak",
                                                       "profit_adj_per_vehicle_day_vnd")})
            demo = int(((g - g.median()).abs() / g.std()).sum(axis=1).idxmin())
            md.append(f"## {SCENES[sc][1]} · {BLACK_BOXES[bb][1]}\n\n{len(ok)} seeds, 48 h, paired by seed. "
                      f"Demo seed: {demo}\n\n" + pd.DataFrame(table).to_markdown(index=False) + "\n")
            manifest.append({"scene": sc, "scene_label": SCENES[sc][1], "bb": bb, "bb_label": BLACK_BOXES[bb][1],
                             "seed": demo, "n": len(ok), "summary": summary})
    # every run, for the "Kết quả" table of the replay page (web/src/results.ts)
    runs = [{"scene": r.scene, "bb": r.bb, "arm": r.arm, "seed": int(r.seed), "m": [float(r[k]) for k in KEYS]}
            for _, r in df.iterrows()]
    WEB.mkdir(parents=True, exist_ok=True)
    (WEB / "ocp1_runs.json").write_text(json.dumps({"keys": KEYS, "runs": runs}), encoding="utf-8")
    (OUT / "ocp1_stats_all.md").write_text("\n".join(md), encoding="utf-8")
    (OUT / "ocp1_manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    print("\n".join(md))


# ---------------- replay export ----------------
def projector(origin):
    tr = Transformer.from_crs("EPSG:4326", "EPSG:32648", always_xy=True)

    def xy(lat, lon):
        x, y = tr.transform(lon, lat)
        return [round(float(x - origin[0]), 1), round(float(y - origin[1]), 1)]
    return xy


def export_arm(scene, bb, arm, seed, xy, label):
    sim = make(scene, bb, arm, seed, log=True)
    m, req, charge, snaps = summarize(sim)
    r = ocp1.router()
    t0, t1 = DAY, 2 * DAY                     # day 2: the fleet has a realistic state of charge
    legs = []
    for vid, a, b, la, lo, la2, lo2, kind, s0, s1, rid in sim.leg_log:
        if b < t0 or a > t1:
            continue
        path = [xy(p[0], p[1]) for p in r.path(la, lo, la2, lo2)]
        legs.append([vid, round(a - t0), round(b - t0), kind, round(s0, 3), round(s1, 3), path])
    states = [[round(t - t0), vid, st, soc, *xy(la, lo), int(stn)]
              for t, vid, st, soc, la, lo, stn in sim.state_log if t <= t1]
    riders = []
    for row in req.itertuples():
        end = row.t_pickup if row.status == "served" else row.t + row.patience_s
        if np.isnan(end):
            end = row.t + row.patience_s
        if end < t0 or row.t > t1:
            continue
        riders.append([round(row.t - t0), round(end - t0), *xy(row.o_lat, row.o_lon),
                       {"served": 0, "cancel_unassigned": 1, "cancel_assigned": 2}.get(row.status, 3)])
    # journeys: same trip ids on both sides (CRN keeps the first bookings identical); first booking on day 2
    journeys = []
    for tid, g in req.groupby("trip_id"):
        g = g.sort_values("attempt")
        first = g.iloc[0]
        if not (t0 <= first.t < t1):
            continue
        srv = g[g.status == "served"]
        end = float(srv.t_pickup.iloc[0]) if len(srv) else float(g.iloc[-1].t + g.iloc[-1].patience_s)
        journeys.append([int(tid), int(len(srv) > 0), round(end - t0), *xy(first.o_lat, first.o_lon)])
    grid = np.arange(0, DAY + 1, 300.0)
    tb, te = req.t.to_numpy() - t0, np.where(req.status == "served", req.t_pickup, req.t + req.patience_s) - t0
    waiting = [int(((tb <= g) & (te > g)).sum()) for g in grid]
    drop = req.t_dropoff.to_numpy() - t0
    served = [int(np.nansum((drop >= 0) & (drop <= g))) for g in grid]
    canc = req[req.status.isin(["cancel_unassigned", "cancel_assigned"])]
    ct = (canc.t + canc.patience_s).to_numpy() - t0
    cancelled = [int(((ct >= 0) & (ct <= g)).sum()) for g in grid]
    st = pd.DataFrame(sim.state_log, columns=["t", "v", "status", "soc", "lat", "lon", "station"])
    st["t"] -= t0
    counts = {k: [] for k in ("charging", "queued", "busy", "idle", "off")}
    socm = []
    for g in grid:
        cur = st[st.t <= g].groupby("v").tail(1)
        s = cur.status
        counts["charging"].append(int((s == "charging").sum()))
        counts["queued"].append(int(s.isin(["queued", "to_station"]).sum()))
        counts["busy"].append(int(s.isin(["to_pickup", "on_trip", "reposition"]).sum()))
        counts["idle"].append(int((s == "idle").sum()))
        counts["off"].append(int(s.isin(["off", "break"]).sum()))
        socm.append(round(float(cur[~s.isin(["off"])].soc.mean()), 3))
    stations = [{"xy": xy(la, lo), "ports": int(p)} for (la, lo), p in zip(sim.stations, sim.ports)]
    out = {"meta": {"scene": scene, "bb": bb, "arm": arm, "seed": seed, "label": label, "duration_s": DAY,
                    "metrics": {k: float(m[k]) for k in KEYS}},
           "stations": stations, "legs": legs, "states": states, "riders": riders, "journeys": journeys,
           "kpi": {"t": grid.tolist(), "waiting": waiting, "served": served, "cancelled": cancelled,
                   "mean_soc": socm, **counts}}
    path = WEB / f"ocp1_replay_{scene}_{bb}_{arm}.json"
    path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    return f"{scene}/{bb}/{arm} seed {seed}: {path.name} ({path.stat().st_size / 1e6:.1f} MB), service {m['service_level']:.3%}"


def export_job(job):
    scene, bb, arm, seed, origin, label = job
    return export_arm(scene, bb, arm, seed, projector(origin), label)


def cmd_export(a):
    base = json.loads((WEB / "oceanpark.json").read_text(encoding="utf-8"))
    manifest = json.loads((OUT / "ocp1_manifest.json").read_text(encoding="utf-8"))
    jobs = []
    for e in manifest:
        jobs += [(e["scene"], e["bb"], "base", e["seed"], base["meta"]["origin"], e["bb_label"]),
                 (e["scene"], e["bb"], "v21", e["seed"], base["meta"]["origin"], e["bb_label"] + " + lớp pin v2.1")]
    with ProcessPoolExecutor(a.jobs) as ex:
        for line in ex.map(export_job, jobs):
            print(line, flush=True)
    (WEB / "ocp1_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stats")
    s.add_argument("--seeds", type=int, nargs=2, default=[1000, 1019])
    s.add_argument("--scenes", nargs="+", default=list(SCENES), choices=SCENES)
    s.add_argument("--bbs", nargs="+", default=list(BLACK_BOXES), choices=BLACK_BOXES)
    s.add_argument("--jobs", type=int, default=4)
    e = sub.add_parser("export")
    e.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    {"stats": cmd_stats, "export": cmd_export}[a.cmd](a)


if __name__ == "__main__":
    main()
