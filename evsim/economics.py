"""Green SM public tariffs (Hanoi, greensm.com) and fleet profit."""

# Green SM Airport Car, Hanoi: package price for either direction (city <-> Noi Bai)
AIRPORT_PACKAGE_VND = 189_000
AIRPORT_PACKAGE_KM = 20
AIRPORT_EXTRA_PER_KM = 9_500


def fare(km, t_s, airport=False):
    """Green SM Car Hanoi, VND, VAT included. Airport trips use the Green Airport package
    (the night surcharge is only listed for metered app trips). Waiting-time and extra-stop
    fees are not modelled."""
    if airport:
        return AIRPORT_PACKAGE_VND + AIRPORT_EXTRA_PER_KM * max(0.0, km - AIRPORT_PACKAGE_KM)
    if km <= 2:
        f = 30_500
    elif km <= 12:
        f = 30_500 + 14_700 * (km - 2)
    elif km <= 25:
        f = 30_500 + 14_700 * 10 + 13_800 * (km - 12)
    else:
        f = 30_500 + 14_700 * 10 + 13_800 * 13 + 11_900 * (km - 25)
    h = (t_s / 3600.0) % 24
    if h >= 22 or h < 6:
        f += 20_000
    return f


def driver_variable_share(cfg):
    """Share of fares paid to drivers: commission for employed drivers, or the whole revenue
    share under the recruitment-page model (kept for sensitivity)."""
    return cfg.driver_commission if cfg.driver_pay == "salary_commission" else cfg.driver_revenue_share


def driver_fixed_vnd_per_day(cfg):
    """Fixed salary per driver per calendar day (one driver per car)."""
    return cfg.driver_fixed_salary_month / 30.0 if cfg.driver_pay == "salary_commission" else 0.0


def fleet_profit(cfg, revenue, kwh_at_plug, total_km, n_strandings, days):
    """Operator view: GSM pays for electricity (driver charging subsidies are internal transfers)
    and driver pay. The fixed salary is identical across dispatch policies, so it shifts the
    level of profit but not the ranking of policies."""
    parts = {
        "revenue": revenue,
        "driver_variable": driver_variable_share(cfg) * revenue,
        "driver_fixed": driver_fixed_vnd_per_day(cfg) * cfg.n_vehicles * days,
        "energy": kwh_at_plug * cfg.price_kwh,
        "other_km": total_km * cfg.other_cost_per_km,
        "towing": n_strandings * cfg.tow_cost,
    }
    parts["profit"] = (revenue - parts["driver_variable"] - parts["driver_fixed"] - parts["energy"]
                       - parts["other_km"] - parts["towing"])
    return parts
