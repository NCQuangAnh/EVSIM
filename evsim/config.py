"""Simulation parameters for the Green SM Car fleet (VinFast VF5). Every value is either
public (GSM / V-Green / VinFast spec), from the mentor's description, or an explicit
assumption meant for sensitivity analysis."""
from dataclasses import dataclass


@dataclass
class Config:
    seed: int = 0
    # Common random numbers: tie every random draw made during the run to the entity it is
    # about (vehicle, request, day), so two policies on one seed meet the same luck. Off keeps
    # the single shared stream used by every run before 2026-10-11 (bit-identical results).
    crn: bool = False
    sim_hours: float = 24.0
    batch_s: int = 30                     # matching window (one Hungarian solve per batch)

    # --- geography (inner Hanoi) ---
    detour: float = 1.3                   # road km = detour * haversine km (assumption)

    # --- fleet: VinFast VF5 ---
    n_vehicles: int = 300
    battery_kwh: float = 37.23            # public spec
    kwh_per_km: float = 0.13              # public spec, sensitivity 0.12-0.18
    soc0_mean: float = 0.6                # SOC when not charged overnight ~ truncated normal on [0, 1]
    soc0_sd: float = 0.2
    # Driver-side charging rule (not part of dispatch): after a drop-off, a driver
    # whose SOC is below their personal threshold drives to a station and charges to
    # soc_target, or to their own level when driver_charge_targets is on. Thresholds vary
    # per driver (assumption).
    soc_threshold_min: float = 0.08
    soc_threshold_max: float = 0.25
    soc_target: float = 1.0
    # Per-driver charging habit (assumption, set 2026-10-04): most drivers unplug somewhere
    # between 60 % and 80 %, a minority charge above 80 %. Overnight charging still fills up.
    driver_charge_targets: bool = False
    charge_target_low_share: float = 0.9
    charge_target_low: tuple = (0.6, 0.8)
    charge_target_high: tuple = (0.8, 1.0)

    # --- driver shifts (off = every vehicle online 24/7) ---
    shifts: bool = False
    # shift groups: (start_lo_h, start_hi_h, share, online_mean_h)
    shift_starts: tuple = ((5.5, 7.5, 0.45, 12.0), (8.0, 11.0, 0.25, 12.0), (13.0, 16.0, 0.20, 12.0),
                           (17.0, 20.0, 0.10, 12.0))
    shift_start_jitter_min: float = 30.0  # day-to-day variation of the same driver
    online_sd_h: float = 1.0
    online_min_h: float = 8.0
    online_max_h: float = 14.0
    max_drive_h_day: float = 10.0         # internal rule: actual driving <= 10 h/day
    max_drive_cont_h: float = 4.0         # internal rule: continuous driving <= 4 h
    drive_cont_margin_h: float = 0.5      # stop taking rides this close to the 4 h limit
    rest_reset_min: float = 15.0          # a stop this long resets continuous driving
    break_min: float = 30.0               # rest break when the 4 h limit is near
    meal_break_min: float = 45.0          # one meal break per shift
    meal_window: tuple = (0.5, 0.5)       # meal due at this fraction of the shift (random in range)
    rest_break_min: float = 0.0           # one extra rest / car-wash break per shift (0 = none)
    rest_window: tuple = (0.6, 0.8)
    meal_charge_soc: float = 0.6          # below this, drivers charge during the meal break
    p_night_charge: float = 0.8           # share of drivers who charge to full overnight (depot/home)
    # A driver who could not drive home with soc_reserve left charges before going off duty.
    # Off reproduces the runs before 2026-10-11, where the drive home could empty the battery
    # and the car started the next shift at ~0 % (the only run-outs seen at full scale).
    charge_before_home: bool = False

    # --- charging stations (public V-Green, shared with private EVs) ---
    n_stations: int = 12
    ports_per_station: int = 8
    external_occupancy: bool = False      # hourly share of ports taken by private EVs
    dc_kw: float = 50.0                   # effective power below taper SOC (assumption)
    taper_soc: float = 0.8
    taper_kw: float = 15.0                # effective power above taper SOC (assumption)
    charge_eff: float = 0.9               # kWh billed at plug = kWh into battery / eff
    tow_min: float = 90.0                 # out-of-service time after running empty
    station_choice_k: int = 5             # drivers compare this many nearest stations
    port_scale: float = 1.0               # stress test: multiply every station's ports (at least 1 kept)
    # Ocean Park 1 demo world (evsim/ocp1.py, docs/OCP1_DATA.md)
    demand_model: str = "hanoi"           # hanoi | ocp1
    ocp1_gateway_share: float = 0.35      # share of OCP1 trips that leave through a gate towards Hanoi
    return_to_area: bool = False          # a free car outside the service area drives back in
    log_moves: bool = False               # keep leg and state logs for the map replay
    typical_charge_min: float = 40.0      # drivers' rule of thumb for one charging session

    # --- demand ---
    daily_requests: int = 7000
    airport_share: float = 0.03
    patience_mean_min: float = 20.0       # rider patience ~ Exponential(mean)

    # --- GSM-like dispatch cost ---
    max_pickup_km: float = 5.0
    w_dist: float = 1.0                   # cost per pickup km
    w_cancel: float = 5.0                 # cost per unit cancellation probability (km-equivalent)
    w_wait: float = 0.2                   # priority bonus per minute the rider has waited

    # --- forward dispatch / repositioning (policy B2) ---
    forward_horizon_min: float = 5.0      # busy vehicles finishing within this can take a rider
    reposition_every_min: float = 5.0
    reposition_idle_min: float = 5.0      # only vehicles idle at least this long are moved
    reposition_horizon_min: float = 30.0  # demand forecast window
    reposition_target_ratio: float = 0.6  # target vehicles per forecast request in the window
    reposition_max_km: float = 15.0
    reposition_soc_margin: float = 0.1    # driver only repositions with SOC above threshold + margin
    # Repositioning is a suggestion; the driver accepts with p = p0 * exp(-km / decay_km)
    # (assumption, sensitivity p0 in 0.3-1.0). A driver who declines is not asked again for a while.
    reposition_accept_p0: float = 0.7
    reposition_accept_decay_km: float = 8.0
    reposition_cooldown_min: float = 15.0

    # --- B3 battery-aware matching (weights chosen on tuning seeds 100+, not the eval seeds) ---
    soc_reserve: float = 0.05             # SOC that must be left on reaching a charger after the trip
    soc_comfort: float = 0.30             # SOC after the trip below which a match is penalised
    w_soc: float = 2.0                    # km-equivalent penalty per 5 % of SOC below soc_comfort
    # B3 charge nudges: idle cars below these SOC levels are sent to charge (checked every 5 min)
    nudge_soc: float = 0.30
    nudge_soc_prepeak: float = 0.50
    nudge_soc_peak: float = 0.15
    nudge_prepeak_hours: tuple = ((6.0, 7.0), (15.5, 17.0))
    nudge_peak_hours: tuple = ((7.0, 9.0), (17.0, 19.0))
    nudge_skip_before_shift_end_min: float = 60.0
    # What the platform knows about each shift end, for that skip rule: exact (registered shifts) |
    # noisy (estimate = true end + N(0, shift_end_noise_min)) | none (rule off: every idle car may be nudged)
    shift_end_info: str = "exact"
    shift_end_noise_min: float = 60.0
    nudge_accept_p: float = 1.0           # share of charge nudges the driver follows (1 = always)
    nudge_cooldown_min: float = 15.0      # a driver who ignored a nudge is not asked again for this long
    # v2.2 supply-aware gate on the raised pre-peak level (time-of-day nudges). Cars below the
    # normal level (nudge_soc) are always nudged; the extra ones (nudge_soc <= SOC < pre-peak level):
    #   none        all of them (v2.1)
    #   idle_share  only while idle cars are at least gate_idle_share of the cars on shift
    #   surplus     at most gate_surplus_frac x (idle cars - waiting riders), lowest SOC first
    nudge_gate: str = "none"
    gate_idle_share: float = 0.2
    gate_surplus_frac: float = 0.5

    # --- B4 DiDi value-based matching (Xu et al., KDD 2018), values from scripts/train_didi_values.py ---
    didi_values: str = "data/didi_values_hanoi_full.npz"
    didi_gamma: float = 0.9               # discount per 10-minute slot (value used in the paper example)
    didi_cancel_aware: bool = False       # our variant: weight the gain by P(rider does not cancel)

    # --- battery module on top of a black box (evsim/battery.py); lambda chosen on seeds 100+ ---
    addon_base: str = "gsm_baseline"      # the black box (B1 proxy of GSM's dispatcher)
    addon_feasible: bool = True           # (a) forbid trips that leave the car unable to reach a charger
    addon_reject: bool = True             # (b) expected battery-decline cost
    addon_nudge: bool = True              # (c) timed charge nudges
    addon_lambda: float = 1.0             # black-box cost of one expected battery decline (tuned on seeds 100-101)
    addon_form: str = "add"               # G(F, B) for (b): add | mult | tiebreak | hard (see BatteryAddOn.combine)
    addon_shift_km: float = 1.0           # mult: the batch's lowest black-box cost is shifted to this value
    addon_tiebreak: float = 0.05          # tiebreak: weight small enough that battery only splits near-ties
    addon_hard_p: float = 0.3             # hard: forbid pairs whose extra decline probability exceeds this
    reject_curve: str = "data/reject_curve.json"  # from scripts/fit_reject_curve.py
    # What the battery layer knows about each driver's habits (docs/driver_model_design.md):
    #   legacy  fleet-wide decline curve (reject_curve) and fixed SOC rules: module v1 behaviour
    #   pooled  the population model: personal charging thresholds are only known as a
    #           distribution over the fleet (what a model with no per-driver data can know)
    #   oracle  each driver's true threshold and decline rule: the ceiling a perfect
    #           behaviour tracker could reach (upper bound for the tracker's value)
    driver_model: str = "legacy"
    # Charge nudges: "time_of_day" = fixed SOC levels by hour (module v1); "smart" = nudge an
    # idle car before a peak when, at the usual drain rate, it would reach its driver's own
    # charging threshold before the peak ends (so it would otherwise charge during the peak)
    nudge_mode: str = "time_of_day"     # time_of_day | smart | hybrid | value (L3) | target (supply target before peaks)
    # target: in the pre-peak windows, nudge just enough idle cars that target_share of the cars on
    # shift will have SOC >= target_soc (charging cars count at their unplug level); cars are taken
    # lowest SOC first, near a free charger first, and never more than the free ports (congestion-aware).
    # Outside the pre-peak windows the time-of-day levels apply.
    target_share: float = 0.85
    target_soc: float = 0.5
    # End-of-shift nudge to charge at home / depot overnight: a driver ending the shift below
    # home_nudge_soc is asked; a share home_nudge_accept of those who would not have charged
    # overnight do (assumption: some drivers have no access to a home charger).
    addon_home_nudge: bool = False
    home_nudge_soc: float = 0.6
    home_nudge_accept: float = 0.5
    nudge_lookahead_h: float = 2.0        # smart: nudge from this long before a peak starts
    drain_soc_per_h: float = 0.06         # smart: SOC used per online hour (~14 km/h x 0.16 kWh/km / 37 kWh)
    smart_nudge_margin: float = 0.03      # smart: SOC margin kept above the threshold
    # Scale of the battery terms: "none" = black-box units (lambda in km for B1), "iqr" = multiples
    # of the interquartile range of the batch's feasible black-box costs (unit-free, same meaning
    # for every black box and unchanged by F -> aF + b).
    addon_scale: str = "none"
    # Bonuses (0 = off). Both are in the same scale as above.
    # Drop-off near a free charger, for cars that will be low after the trip: they can plug in
    # right after the drop-off instead of driving empty to a station (needs live charger state).
    addon_station_bonus: float = 0.0
    station_bonus_soc: float = 0.35       # full bonus at SOC after trip <= this - 0.15, none above it
    station_bonus_radius_km: float = 2.0  # bonus falls linearly to 0 at this drop-off-to-charger distance
    # Before the peaks, when there are more cars than riders, prefer well-charged cars so the
    # low ones stay free to be nudged to charge (a per-car term: it only changes WHICH cars serve).
    addon_prepeak_bonus: float = 0.0
    # Coupling the safety mask (a) to charging: an idle car that (a) shuts out of most of the
    # batch's trips is nudged to charge at the next nudge round instead of idling as dead
    # capacity (seen with late chargers, batch dev2).
    # Interface level the black box offers the battery layer (docs/framework_spec.md):
    #   0 assignments only: (a) becomes a veto of the solved pairs, no (b); nudges still run
    #   1 score matrix F: (a) mask and (b) in G, but SOC of forward candidates taken as now
    #   2 + candidate state: SOC when a forward candidate becomes free (all runs so far)
    #   3 + value: with a black box exposing V (B4c), nudge_mode="value" times charging by V
    addon_level: int = 2
    addon_mask_nudge: bool = False
    mask_nudge_share: float = 0.8         # flag a car when at least this share of its batch trips is masked
    mask_nudge_km: float = 12.0           # ...or when its SOC cannot cover a typical trip (pickup + ride + way to a
                                          # charger, ~12 km) and still keep soc_reserve: the mask makes it near-useless
    # (a') soft low-margin penalty: pairs that are safe but leave less than soft_margin_width
    # SOC above the reserve at the nearest charger pay up to addon_soft_margin x scale
    addon_soft_margin: float = 0.0
    soft_margin_width: float = 0.07
    soc_info: str = "exact"               # exact | noise | stale | coarse (information ablation)
    soc_noise_sd: float = 0.05
    soc_report_min: float = 5.0
    soc_coarse_step: float = 0.25

    # --- driver accepts / rejects ride offers (all assumptions) ---
    driver_accept: bool = False
    ride_accept_base: float = 0.95        # acceptance for non-battery reasons
    ride_reject_per_far_km: float = 0.03  # extra rejection per pickup km beyond 3 km
    # Drivers see the destination and reject when the trip would leave them near their own
    # charging threshold: p_reject_soc = sigmoid((threshold + margin - soc_after) / scale).
    driver_soc_decline: bool = True       # False: drivers never decline because of battery (robustness test)
    ride_reject_soc_margin: float = 0.05
    ride_reject_soc_scale: float = 0.02
    ride_response_s: float = 8.0          # mean time to tap "accept"
    # Heterogeneous, noisy drivers (T1 of docs/driver_model_design.md). Off = every driver follows
    # the same rule with only a personal threshold (all runs before 2026-10-11).
    driver_hetero: bool = False
    hetero_thr_noise_sd: float = 0.03     # threshold drawn afresh around the personal value at each decision
    hetero_end_shift_max: float = 0.10    # per-driver extra threshold in the last 2 h of the shift, U(0, max)
    hetero_margin: tuple = (0.0, 0.10)    # per-driver decline margin (replaces ride_reject_soc_margin)
    hetero_scale: tuple = (0.01, 0.05)    # per-driver decline sharpness (replaces ride_reject_soc_scale)
    hetero_target_sd: float = 0.05        # unplug level varies around the personal target per session
    nudge_accept_mean: float = 0.6        # per-driver nudge compliance ~ Beta with this mean...
    nudge_accept_kappa: float = 2.0       # ...and this concentration (2 = very spread, many near 0 or 1)

    # --- expanding search radius ---
    radius_expand: bool = False
    pickup_radius0_km: float = 2.5
    radius_growth_km_per_min: float = 1.0  # radius grows with rider waiting time up to max_pickup_km

    # --- driver fairness: prefer drivers idle longer ---
    w_idle: float = 0.0                   # km-equivalent bonus per idle minute (capped)
    idle_bonus_cap_min: float = 30.0

    # --- going-home mode near shift end ---
    home_mode: bool = False
    home_mode_min: float = 60.0           # last minutes of the shift
    home_radius_km: float = 3.0           # trips ending within this of home are always fine

    # --- riders cancel and rebook ---
    rebook: bool = False
    p_early_cancel: float = 0.05          # cancels within 0.5-3 min regardless of ETA
                                          # (wrong address, price check, changed mind)
    p_rebook_early: float = 0.6
    p_rebook_unassigned: float = 0.5
    p_rebook_assigned: float = 0.6
    rebook_delay_mean_min: float = 1.5
    rebook_patience_factor: float = 0.7   # a rebooking rider is less patient
    max_attempts: int = 3

    # --- real-world geography (built by scripts/build_osm_data.py) ---
    road_network: bool = False            # OSM road distances between ~1 km grid cells
    real_stations: bool = False           # real charging stations instead of synthetic ones
    station_source: str = "osm"           # osm (scripts/build_osm_data.py) | google (scripts/fetch_google_stations.py)
    # Google gives nominal power for a few stations; the car limits what it can draw (assumptions,
    # check against the VF5 spec). DC power is scaled down to an average over the charging curve.
    vehicle_max_dc_kw: float = 50.0       # VF5 DC max 50 kW, AC 6.6 kW (dealer/press spec sheets)
    vehicle_max_ac_kw: float = 6.6
    dc_curve_factor: float = 0.8

    # --- economics (VND) ---
    price_kwh: float = 3858.0             # V-Green public price
    # Driver pay. greensm.com driver FAQ: fixed salary (incl. social insurance) + commission
    # "up to 25% of total revenue"; recruitment pages quote ~5.31M fixed and 15-18M/month
    # guaranteed, which matches salary + 25% at simulated revenue. "revenue_share" uses the
    # recruitment headline "revenue share up to 60-62%" instead (sensitivity).
    driver_pay: str = "salary_commission"  # salary_commission | revenue_share
    driver_fixed_salary_month: float = 5_310_000.0
    driver_commission: float = 0.25
    driver_revenue_share: float = 0.62
    other_cost_per_km: float = 0.0        # maintenance/tyre/depreciation, sensitivity 0-300
    tow_cost: float = 800_000.0           # assumption


# share of public ports occupied by private EVs, by hour of day (assumption)
EXTERNAL_OCCUPANCY = (0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.3, 0.3, 0.3, 0.4, 0.5,
                      0.5, 0.5, 0.4, 0.4, 0.4, 0.5, 0.6, 0.6, 0.6, 0.5, 0.4, 0.3)

SCENARIOS = {
    # original setting: 24 h, every vehicle online all day, spare chargers
    "base": dict(),
    # realistic shifts, 3 days, fewer public ports shared with private EVs, taxi-like
    # consumption (A/C, stop-and-go), half the drivers without overnight charging.
    # Calibrated so drivers spend ~1.3 h/day going to, queuing at and using chargers.
    "stress": dict(sim_hours=72.0, shifts=True, n_stations=8, ports_per_station=6,
                   external_occupancy=True, kwh_per_km=0.16, p_night_charge=0.5, dc_kw=40.0),
}
# stress + driver acceptance, expanding radius, fairness, going-home mode, rebooking
SCENARIOS["realistic"] = dict(SCENARIOS["stress"], driver_accept=True, radius_expand=True,
                              w_idle=0.1, home_mode=True, rebook=True, driver_charge_targets=True)
# realistic + OSM road distances and OSM charging stations
SCENARIOS["realistic_osm"] = dict(SCENARIOS["realistic"], road_network=True, real_stations=True,
                                  ports_per_station=4)   # ports assumed where OSM has no capacity tag
# realistic_osm with Google Places stations (ports and power where Google has them)
SCENARIOS["realistic_google"] = dict(SCENARIOS["realistic_osm"], station_source="google")

# Shift mix calibrated to the target share of the fleet on the road (idle or serving):
# 75-85% at 7-9h and 17-19h, 50-60% midday (meal breaks and charging), 15-20% at 23-5h.
# Most drivers work ~6:00-19:00, a night group ~19:00-7:30, a small late group ~10:00-22:00.
GAMMA_SHIFTS = ((5.5, 6.5, 0.70, 13.0), (10.0, 11.0, 0.10, 12.0), (18.5, 19.5, 0.20, 12.5))
# full Hanoi fleet (~5,080 cars in the simulated area) at ~23 bookings per car per day
SCENARIOS["hanoi_full"] = dict(SCENARIOS["realistic_google"], shift_starts=GAMMA_SHIFTS,
                               online_sd_h=0.5, n_vehicles=5080, daily_requests=118_533,
                               # breaks spread over the day: meal ~10-13h, rest/car wash ~14-16h30
                               meal_window=(0.3, 0.5), rest_break_min=40.0, rest_window=(0.55, 0.72))

# Ocean Park 1 demo (docs/OCP1_DATA.md): same drivers, shifts, economics and protocol as hanoi_full,
# on the OCP1 road graph with 60 cars, 1,276 bookings/day and 40 car charger ports.
SCENARIOS["ocp1_demo"] = dict(SCENARIOS["hanoi_full"], road_network="ocp1", demand_model="ocp1",
                              real_stations=True, station_source="ocp1", n_vehicles=60, daily_requests=1276,
                              airport_share=0.0, return_to_area=True, driver_hetero=True, crn=True,
                              charge_before_home=True, sim_hours=48.0)
