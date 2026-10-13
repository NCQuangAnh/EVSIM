import numpy as np
import pandas as pd

from .economics import driver_fixed_vnd_per_day, driver_variable_share, fare, fleet_profit

PEAK_HOURS = (7, 8, 17, 18)
CHARGING_STATES = ["to_station", "queued", "charging"]


def summarize(sim):
    cfg = sim.cfg
    days = cfg.sim_hours / 24
    req = pd.DataFrame([r.__dict__ for r in sim.requests])
    # rider experience is measured from the journey's first booking (rebookings included)
    req["t_first"] = req.groupby("trip_id").t.transform("min")
    served = req[req.status == "served"]
    wait_min = (served.t_pickup - served.t_first) / 60
    serve_min = (served.t_dropoff - served.t_first) / 60
    in_peak = ((req.t_first / 3600) % 24).astype(int).isin(PEAK_HOURS)
    peak = served[in_peak[served.index]]

    km = {k: sum(v.km[k] for v in sim.vehicles) for k in ("deadhead", "trip", "to_station", "reposition", "home")}
    total_km = sum(km.values())
    duty_km = total_km - km["home"]
    charge = pd.DataFrame(sim.charge_log,
                          columns=["vehicle", "station", "t_queued", "t_start", "t_end", "soc_from", "soc_to"])
    snaps = pd.DataFrame(sim.snapshots, columns=["t", "vehicle", "status", "soc"])
    snaps["hour"] = ((snaps.t / 3600) % 24).astype(int)
    online = snaps[snaps.status != "off"]
    peak_online = online[online.hour.isin(PEAK_HOURS)]

    online_h = np.array([v.online_s for v in sim.vehicles]) / 3600 / days
    drive_h = np.array([v.drive_s for v in sim.vehicles]) / 3600 / days
    charge_h = ((charge.t_end - charge.t_queued).sum() / 3600 / cfg.n_vehicles / days) if len(charge) else 0.0
    to_station_h = km["to_station"] / cfg.n_vehicles / days / 22.0   # rough, avg speed

    kwh = sim.kwh_at_plug + sim.kwh_night
    money = fleet_profit(cfg, served.fare.sum(), kwh, total_km, sim.strandings, days)
    share = driver_variable_share(cfg)
    stock_kwh = getattr(sim, "e_end_kwh", 0.0) - getattr(sim, "e0_kwh", 0.0)
    stock_vnd = stock_kwh / cfg.charge_eff * cfg.price_kwh

    # A journey (trip_id) may be booked several times after cancellations. It is served if any
    # booking was served; otherwise its fare is lost, attributed to the last booking's outcome.
    req["fare_potential"] = [fare(k, t, a) for k, t, a in zip(req.trip_km, req.t, req.airport)]
    last = req.sort_values("attempt").groupby("trip_id").last()
    trip_served = req.groupby("trip_id").status.apply(lambda s: (s == "served").any())
    unserved = last[~trip_served.reindex(last.index).to_numpy()]
    lost = {s: unserved.loc[unserved.status == s, "fare_potential"].sum() / days
            for s in ("cancel_assigned", "cancel_unassigned", "failed_stranded")}
    lost_total = sum(lost.values())

    # driver side
    online_s = np.array([v.online_s for v in sim.vehicles])
    trip_s = np.array([v.trip_s for v in sim.vehicles])
    earn = (served.groupby("vehicle").fare.sum() * share
            ).reindex(range(cfg.n_vehicles), fill_value=0.0).to_numpy()
    earn = earn + driver_fixed_vnd_per_day(cfg) * days
    active = online_s > 0
    earn_per_h = earn[active] / (online_s[active] / 3600)

    # supply vs demand at peak
    peak_req_per_h = req[in_peak].trip_id.nunique() / (len(PEAK_HOURS) * days)
    peak_online_n = online[online.hour.isin(PEAK_HOURS)].groupby("t").size().mean()
    n = len(req)
    out = {
        "requests": n,
        "trips": len(trip_served),
        "service_level": trip_served.mean(),          # share of journeys eventually served
        "request_fill_rate": len(served) / n,          # share of bookings served
        "rebooks_per_day": sim.rebooks / days,
        "service_level_peak": trip_served[req[in_peak].trip_id.unique()].mean(),
        "cancel_unassigned": (req.status == "cancel_unassigned").mean(),
        "cancel_assigned": (req.status == "cancel_assigned").mean(),
        "failed_stranded": (req.status == "failed_stranded").mean(),
        "wait_min_mean": wait_min.mean(),
        "wait_min_p90": wait_min.quantile(0.9),
        "wait_min_peak_mean": ((peak.t_pickup - peak.t_first) / 60).mean(),
        "serving_min_mean": serve_min.mean(),
        "deadhead_ratio": (km["deadhead"] + km["to_station"] + km["reposition"]) / duty_km,
        "home_km_day": km["home"] / days,
        "ride_offers_per_day": sim.ride_offers / days,
        "ride_reject_rate": sim.ride_rejects / sim.ride_offers if sim.ride_offers else 0.0,
        "ride_reject_soc_share": sim.ride_rejects_soc / sim.ride_rejects if sim.ride_rejects else 0.0,
        "reposition_km_day": km["reposition"] / days,
        "reposition_offers_per_day": sim.repo_offers / days,
        "repositions_per_day": sim.repositions / days,
        "reposition_accept_rate": sim.repositions / sim.repo_offers if sim.repo_offers else np.nan,
        "forward_assign_share": sim.forward_assigns / max(1, req.t_assign.notna().sum()),
        "strandings_per_day": sim.strandings / days,
        "charge_sessions_per_day": len(charge) / days,
        "charge_nudges_per_day": getattr(sim, "charge_nudges", 0) / days,
        "charge_queue_min_mean": ((charge.t_start - charge.t_queued) / 60).mean() if len(charge) else 0.0,
        "charge_soc_from_mean": charge.soc_from.mean() if len(charge) else np.nan,
        "charge_soc_to_mean": charge.soc_to.mean() if len(charge) else np.nan,
        "charge_session_min_mean": ((charge.t_end - charge.t_start) / 60).mean() if len(charge) else np.nan,
        "driver_online_h_day": online_h.mean(),
        "driver_drive_h_day": drive_h.mean(),
        "driver_charging_h_day": charge_h + to_station_h,
        "shifts_cut_by_10h_rule": sum(v.shifts_ended_by_drive_cap for v in sim.vehicles),
        "utilization": trip_s.sum() / online_s.sum(),
        "idle_share_online": (online.status == "idle").mean(),
        "driver_earn_per_online_h_vnd": earn_per_h.mean(),
        "driver_earn_per_online_h_p10_vnd": np.quantile(earn_per_h, 0.1),
        "driver_earn_per_online_h_p90_vnd": np.quantile(earn_per_h, 0.9),
        "driver_earn_cv": earn_per_h.std() / earn_per_h.mean(),
        "peak_online_vehicles": peak_online_n,
        "peak_requests_per_h": peak_req_per_h,
        "peak_vehicles_per_request_h": peak_online_n / peak_req_per_h if peak_req_per_h else np.nan,
        "peak_share_charging": peak_online.status.isin(CHARGING_STATES).mean(),
        "peak_share_low_soc": (peak_online.soc < 0.2).mean(),
        "kwh_public_per_day": sim.kwh_at_plug / days,
        "kwh_night_per_day": sim.kwh_night / days,
        "revenue_vnd_day": money["revenue"] / days,
        "energy_cost_vnd_day": money["energy"] / days,
        "towing_cost_vnd_day": money["towing"] / days,
        "lost_fare_vnd_day": lost_total,
        "lost_fare_cancel_assigned_vnd_day": lost["cancel_assigned"],
        "lost_fare_cancel_unassigned_vnd_day": lost["cancel_unassigned"],
        "lost_fare_stranded_vnd_day": lost["failed_stranded"],
        "lost_margin_gsm_per_vehicle_day_vnd": lost_total * (1 - share) / cfg.n_vehicles,
        "driver_pay_vnd_day": (money["driver_variable"] + money["driver_fixed"]) / days,
        "driver_income_month_vnd": (money["driver_variable"] + money["driver_fixed"]) / days
                                   / cfg.n_vehicles * 30,
        "wasted_deadhead_km_day": req.wasted_km.sum() / days,
        "profit_vnd_day": money["profit"] / days,
        "profit_per_vehicle_day_vnd": money["profit"] / cfg.n_vehicles / days,
        # energy left in the batteries is bought electricity not yet used: value it at the grid
        # price so a policy ending the run with fuller batteries is not charged for it
        "energy_stock_change_kwh_day": stock_kwh / days,
        "energy_cost_adj_vnd_day": (money["energy"] - stock_vnd) / days,
        "profit_adj_per_vehicle_day_vnd": (money["profit"] + stock_vnd) / cfg.n_vehicles / days,
        "charge_nudge_offers_per_day": getattr(sim, "nudge_offers", 0) / days,
        "home_runouts_per_day": getattr(sim, "home_runouts", 0) / days,
        "home_nudges_per_day": getattr(sim, "home_nudges", 0) / days,
    }
    for kind in ("deadhead", "trip", "to_station", "reposition"):
        out[f"strand_{kind}_per_day"] = sum(e["kind"] == kind for e in getattr(sim, "strand_log", [])) / days
    return out, req, charge, snaps
