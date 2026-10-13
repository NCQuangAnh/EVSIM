# Work log: battery framework (Nhóm 2, VRIC × GSM)

Read this first when resuming. It records state, decisions and results that are not obvious from the code. Newest entries at the bottom of each section. All numbers are simulation results.

## How to run things

- Python: always `.venv/Scripts/python` (the `python` on PATH belongs to another project).
- Experiments: `scripts/experiments.py` (catalogue + `BATCHES`) and `scripts/run_jobs.py run|status|merge|summarize --batch <name>`.
  - One JSON per arm × seed in `outputs/jobs/<experiment>/`. Jobs are resumable and shardable.
  - The summary is written to `outputs/jobs_<batch>_summary.md`.
- Kaggle:
  1. `kaggle/make_bundle.py` writes `kaggle/evsim_bundle/`; upload it as a new version of dataset `minh12605/evsim-vric` (path `/kaggle/input/datasets/minh12605/evsim-vric`).
  2. `kaggle/make_notebook.py` writes `kaggle/evsim_jobs.ipynb` (parameters `BATCH`, `SHARD`, `NSHARDS`, default 5).
  3. The user runs the copies in parallel (CPU, Internet on): 14 for dev1–dev34, 5 since dev5.
  4. Download `jobs_<batch>_shard<k>.zip` → `run_jobs.py merge <zips>` → `summarize`.
  5. **Re-run make_bundle after every code change.**
- Old pipelines (still valid for history):
  - `run_baseline.py` with the run registry `outputs/runs/index.csv`;
  - `scripts/run_ablation.py` (v1 ablation on seeds 0–4; tables in `outputs/ablation/`);
  - `scripts/dev_ablation.py` (local dev groups);
  - `scripts/dev_variance.py`.
- Regression check: with every new flag off (`crn`, `charge_before_home`, bonuses, `addon_scale`), results are bit-identical to the pre-2026-10-11 code. This was verified on 5 policies, 400 cars, 30 h.
- Unit test: `tests/test_battery_scale.py`. There is no pytest; run the function directly. It checks that the assignment is unchanged under F → aF + b when `addon_scale="iqr"`.

## Documents

- `docs/framework_spec.md`: the framework. The battery layer sits around a dispatch rule. Interface levels:
  - L0: assignments only;
  - L1: score matrix F;
  - L2: candidate/state hooks;
  - L3: value V or forecast.
- The spec also lists the guarantees and the components (a), (a'), (b), (c), (c'), (d) station bonus, (e) pre-peak bonus.
- Figure: `docs/figures/battery_framework.png` (`scripts/plot_framework.py`). Older pipeline figure: `docs/figures/pipeline_battery_addon.png`.
- `docs/protocol.md`: evaluation protocol.
  - Seeds: fit 200–201; development 300–319; evaluation 1000–1019 (untouched until the module is locked).
  - Non-inferiority margins: 0.1 pt service, 2,000 VND/car/day on the inventory-adjusted profit.
  - Holm correction; equal-weight average over black boxes.
  - Black boxes: B0 greedy, B1, B2-F, B2-R, B2, B6 immediate value, B4c.
- `docs/mentor_update.md`: v1 write-up for mentor Huy Hoàng (to be rewritten as G(F, B) after v2). The user wants to finish a robust framework first and write the report once.

## Decisions (user / friend review)

- Mentor: model as G(F, B), where F is the company cost (black box, values only) and B is battery information. Black box = B1.
- Charging habit: 90 % of drivers unplug at 60–80 %, 10 % at 80–100 %, and overnight charging fills to 100 %.
- Margins 0.1 pt and 2,000 VND are fixed. If power is short, add seeds instead of widening the margins.
- Friend's review accepted:
  - logistic decline model with a counterfactual q_pin;
  - IQR-scaled penalty;
  - hard safety mask vs soft low-margin penalty;
  - `nudge_accept_p`;
  - congestion-aware nudges, where the driver still picks the station;
  - more black boxes;
  - CRN;
  - OOD screening at 1,000 cars, with the worst case at full scale.
- The user asked for bonuses as well: station bonus and pre-peak bonus (done).

## Code state (2026-10-11)

- `evsim/simulator.py`:
  - `crn` (hash-based draws tied to vehicle/request/day);
  - `nudge_accept_p` + `nudge_cooldown_min`;
  - `charge_before_home`;
  - `strand_log`, `home_runouts`, and energy stock `e0_kwh` / `e_end_kwh`.
- `evsim/metrics.py`:
  - `energy_cost_adj_vnd_day`, `profit_adj_per_vehicle_day_vnd`;
  - `strand_<kind>_per_day`, `home_runouts_per_day`, `charge_nudge_offers_per_day`.
- `evsim/battery.py` `BatteryAddOn`:
  - (a) mask, (b) via `combine` (forms add / mult / tiebreak / hard), (c) nudges;
  - `addon_scale` none|iqr;
  - `addon_station_bonus`;
  - `addon_prepeak_bonus`.
- Not yet built (phase 1–2):
  - logistic decline model + counterfactual q_pin;
  - soft low-margin penalty (a');
  - congestion-aware nudges;
  - rank form;
  - B0 greedy and B6 immediate-value black boxes;
  - interface-level gating L0–L3;
  - value-timed charging (c').

## Results (development, 1,000 cars, seeds 300–309, CRN + charge_before_home unless noted)

- **Run-outs at full scale (old runs, 0.27/day).** They were not caused by dispatch. The drive home could empty the battery without any check, and the car then stranded the next morning on the way to a charger (B1 seed 3: 2 events on `to_station` legs at 06:18 and 10:34, plus 1 drive home). Fixed by `charge_before_home`.
- **Variance.** CRN cuts the sd of the paired service difference from 0.181 to 0.093 pt, and the sd of the profit difference from 2,789 to 1,852 VND. With CRN, 5 seeds are enough for the margins.
- **Bonus group** (local, `outputs/dev/bonus_table.md`):
  - every arm with (c) gives about +0.35 pt service and +5.7–6.0k VND profit;
  - bonuses add nothing on top of (c);
  - the station bonus cuts the charger queue (−0.09 min vs full IQR);
  - the station bonus alone gives +0.06 pt (LCB +0.01) and +1.4k VND, both significant. It is the first matching-side component that helps on its own.
- **Kaggle batch dev1** (400 jobs, fingerprint matched, `outputs/jobs_dev1_summary.md`):
  - Nudge compliance p = 1 / 0.7 / 0.5 / 0.3 / 0 → +0.37 / +0.35 / +0.28 / +0.24 / +0.03 pt. All gain comes from (c), and 30 % compliance keeps about 2/3 of it.
  - The reserve of (a) (0–8 %) hardly matters.
  - (b) alone with IQR λ = 4 fails non-inferiority (−0.07 pt, −3.5k). Keep λ ≤ 1.
  - Bigger bonuses add nothing on top of (c).
  - The module improves all 5 black boxes: B1 +0.34, B2-F +0.33, B2-R +0.38, B2 +0.31, B4c +0.41 pt; profit +5.1 to +6.6k. All pass goals B and C.
  - Caveat: B4c at 1,000 cars uses V learned at 5,080 cars.

- **Kaggle batch dev2** (280 jobs, `outputs/jobs_dev2_summary.md`; service in pt vs B1 of the same world):
  - **Drivers never decline for battery.**
    - B1 has 1.20 run-outs/day per 1,000 cars; every arm with (a) cuts it to about 0.03.
    - (c) alone gives +0.12 pt (run-outs −1.00); (a)(b)(c) gives +0.13 pt and +2.1k.
    - (a) alone: −0.04 pt. It is a pure safety layer.
    - **The station bonus alone fails non-inferiority (−0.04, LCB −0.11)**, and with (a)(b)(c) it lowers the gain to +0.07.
  - **Late chargers** (threshold 3–12 %).
    - (c) +0.18; (a)(c) +0.15; **(a)(b)(c) +0.23 pt (best, +2.9k)**.
    - **(a) alone fails (−0.09 pt, −1.8k)**: drivers sit below the mask boundary but do not go to charge, so the cars become dead capacity. This is the same mechanism as the hard filter.
  - **30 % nudge compliance.** (c) +0.26 pt; the matching side adds nothing significant.
  - **No declines + 30 % compliance.** (c) +0.18 pt; (a)(c) +0.18 pt with run-outs −1.17 and the best profit (+3.3k).
  - Lessons:
    1. (a) is worth keeping only as safety and must be coupled to a charge action. To build: a mask-triggered nudge, i.e. a car masked out of most trips is nudged to charge (and/or the soft margin (a')).
    2. The legacy station bonus is not robust; keep it off unless it is personalised (dev3 tests the pooled / oracle weighting).
    3. (b) helps a little only with late chargers.

- **dev3: driver-model ceiling (T0).** Oracle − pooled, paired over 10 seeds:
  - base world: (a)(b)(d) + time-of-day (c) +0.02 ± 0.08 pt; smart (c) only +0.02 ± 0.07; (a)(b)(d) + smart (c) **+0.08 ± 0.05 pt, +1.3k ± 1.2k** (the largest);
  - no battery declines and late chargers: about 0 or negative.
  - **Gate T0 is not reached** (needs ≥ 0.1 pt or ≥ 2k). In this simulator, knowing each driver's threshold adds little over the population model.
  - Pooled − legacy: +0.03 to +0.07 pt (n.s.).
  - **Smart nudges (pooled, no per-driver data) vs time-of-day:**
    - charger queue −0.27 min in every world;
    - no-declines world: +0.19 ± 0.06 pt and +3.6k;
    - base world: peak service −0.50 pt;
    - late chargers: about equal.
    - So smart is better at queues and when drivers do not self-manage, worse for peak service in the base world. A hybrid is worth testing.
- **dev4: coupling the mask (a) to charging.**
  - (a) + mask nudge at 30 km fixes "(a) alone": late chargers go from −0.09 ✗ to **+0.11 pt, +1.6k ✓**; base +0.09; no declines +0.02 with run-outs −1.17.
  - At 12 / 20 km it is about 0.
  - The soft margin (a') is useless, and hard + soft fails ✗ for late chargers and no declines → **drop (a')**.
  - With (c), the extra (a) / mask brings safety only (service about equal).
- Decisions after dev34:
  1. Keep (a) only with mask nudge at 30 km, or together with (c).
  2. Drop (a') and the fixed station bonus.
  3. Do not build the full per-driver tracker yet. Either add realistic driver heterogeneity first (T1: heterogeneous nudge compliance, noisy or time-varying thresholds), where personalisation might matter, or move on with the pooled model.
  4. Test a hybrid nudge: smart off-peak / pre-peak + time-of-day floor.

- **dev5: T1 with heterogeneous drivers** (`outputs/jobs_dev5_summary.md`).
  - **Oracle − pooled is about 0 again** (largest: hybrid +0.04 ± 0.05 pt, +0.7k). **Gate T0 fails a second time**, so the per-driver tracker is not built. It stays a design (`docs/driver_model_design.md`) to revisit only if GSM logs show stronger heterogeneity.
  - **Time-of-day nudges beat smart and hybrid** under heterogeneity: v2 smart / hybrid − v2 time-of-day = −0.23 / −0.26 pt service, −0.8 pt peak, −4k profit (hetero); −0.13 pt (hetero + late). The broad pre-peak top-up (< 50 % before the peaks) is what matters. Smart nudges are dropped.
  - v2 time-of-day: legacy ≈ pooled ≈ oracle, +0.34 pt / +5.7k (hetero) and +0.26–0.29 pt / +4.1–4.4k (hetero + late). All pass.
  - **Module v2 candidate (to lock after the black-box batch):** (a) + mask nudge 30 km; (b) IQR λ 0.5 with the legacy curve; (c) time-of-day nudges; no station / pre-peak bonus, no (a').

- **dev6 bb7** (heterogeneous drivers): module v2 passes on all 7 black boxes.
  - Service: B0 +0.40, B1 +0.34, B2-F +0.30, B2-R +0.39, B2 +0.33, **B6 +0.52**, B4c +0.35 pt; equal-weight average ≈ +0.38 pt.
  - Profit adj: +5.4 to +6.7k; average ≈ +6.2k VND/car/day.
  - The weaker black boxes (B0 greedy, B6 immediate value) gain the most.
- **dev6 levels: the hypothesis "higher interface level → more gain" is NOT supported.**
  - L0 (veto only, no (b)) ≈ L1 ≈ L2: B4c L0 − L2 −0.01 ± 0.05 pt; B2 L0 − L2 +0.04 ± 0.08.
  - L3 (V-timed nudges) is *worse*: −0.06 ± 0.06 pt, peak −0.19, −2.0k, although the charger queue is −0.14 min.
  - Practical consequence: the framework needs only **L0 + SOC telemetry + the ability to send nudges**. Report this as the requirement, and the level ablation as evidence. Revise `docs/framework_spec.md`.
- **dev7 nudge_design** (B1). The pre-peak level is the lever:
  - 40 % is much worse (+0.16–0.19);
  - 50 % for 2 h: +0.37;
  - **60 % for 2 h: +0.47 pt, +7.6k** (vs default: +0.12 ± 0.09 pt, peak +0.32, +1.9k ± 1.4k, energy +575k VND/day per 1,000 cars);
  - **target 80 % at SOC 60 %: +0.44 pt, peak +1.65 (best peak), +7.0k** (vs default +0.10 ± 0.06, peak +0.48);
  - off-peak 40 %: +0.03; home nudge: +0.03 on top (+0.11 alone), energy −193k.
  - The trend is still rising at 60 %, hence dev8.

- **dev8 schedule** (B0 / B1 / B4c, mean over the 3 black boxes):
  - pre-peak 70 % 2 h + off-peak 40 % + home 60 %: +0.51 pt, peak +1.68, +8.4k;
  - **pre-peak 70 % 2.5 h: +0.50 pt, peak +1.65, +7.9k**;
  - pre-peak 60 % 2 h: +0.47; pre-peak 70 % 2 h: +0.44; target 80 % at 60 %: +0.44;
  - pre-peak 80 % 2 h: +0.42; v2 default: +0.37; target 80 % at 70 %: +0.33.
  - Plateau around 60–70 % over 2–2.5 h; 80 % and a 70 % target overshoot.
  - **Locked v2.1 = v2 + pre-peak 70 % for 2.5 h** (no home-charging assumption); home nudge kept as a separate variant. Lock recorded in `docs/protocol.md`.

- **FINAL EVALUATION eval1** (full scale, heterogeneous drivers, seeds 1000–1019, `outputs/eval_main_report.md`).
  - **Goal B passed for all 7 black boxes** on both metrics (Holm p < 1e-4).
  - Service gain: B0 +0.63, B1 **+0.69**, B2-F +0.34, B2-R +0.81, B2 +0.41, B6 +0.72, B4c +0.35 pt.
  - Profit adj: +4.9 to +12.2k VND/car/day (B1 +10.4k).
  - **Goal C: +0.564 pt (LCB +0.551), +8,264 VND/car/day (LCB +8,027); 100 % of seeds gain.**
  - "+ home" variant: B1 +0.84 pt / +13.4k; B4c +0.54 / +8.8k.
  - Secondary metrics:
    - peak service +0.6 to +2.3 pt;
    - wait P90 −0.2 to −0.9 min (B6 +0.07);
    - battery share of declines −15 to −21 pt;
    - cars charging at peak −1.5 to −2.9 pt;
    - **charger queue −0.2 to −2.6 min**, or ≈ 0 for B2 / B2-F;
    - energy +7 to +12 M VND/day for the fleet;
    - driver income +0.06 to +0.15 M VND/month;
    - earnings CV unchanged.

- **ood1** (1,000 cars, seeds 1000–1009, locked v2.1). Mean over 7 black boxes:
  - demand −20 %: +0.40 pt / +4.6k;
  - **demand +20 %: +0.18 pt / +3.4k**;
  - ports × 0.6: +0.55 / +8.3k;
  - harsh (0.20 kWh/km, noisy SOC, compliance 0.4): **+0.65 / +9.8k** (largest).
  - **The only failure: B0 with demand +20 %**: −0.01 pt (LCB −0.09, still ✓) but profit −1.2k (LCB −2.6k ✗ for the 2,000 margin). B6 with demand +20 % is borderline (+0.08, LCB −0.02; profit LCB −0.4k ✓).
  - Interpretation: when supply is scarce, pulling cars off the road at 70 % before the peaks costs trips, most of all for the inefficient greedy matcher.
  - Candidate fix (needs a new dev cycle and fresh seeds): a supply-aware gate on the pre-peak nudges, e.g. nudge only when the idle share is above a threshold.

- **dev9: supply gate** (dev seeds, 1,000 cars).
  - Base world: surplus 0.5 gives B0 +0.55 / B1 +0.48 / B6 +0.72 pt, against v2.1 at +0.50 / +0.52 / +0.68.
  - Demand +20 %: surplus 0.5 gives B0 +0.18 (+3.1k) / B1 +0.24 (+4.2k) / B6 +0.24 (+2.9k), against v2.1 at +0.10 (+0.9k) / +0.17 (+2.7k) / +0.13 (+1.1k).
  - Idle-share gates cut peak gains (25 % is bad).
  - **Locked v2.2 = v2.1 + surplus gate 0.5** (`docs/protocol.md`).

- **ood2: demand +20 % at full scale** (v2.1, seeds 1000–1019). **All 7 black boxes pass** both margins (Holm).
  - Service: B0 +0.52, B1 +0.74, B2-F +0.51, B2-R +0.74, B2 +0.57, B6 +0.39, B4c +0.48 pt.
  - Profit: +6.7 to +13.6k.
  - Goal C: +0.564 pt (LCB +0.543), +10.3k (LCB +9.8k), 100 % of seeds.
  - So the B0 failure in ood1 was a small-scale effect: 1,000 cars on a quarter of the demand is a sparser, harder supply.
  - v2.1 remains the locked main result (eval1 + ood2). v2.2 is evaluated as an improvement on fresh seeds (eval2).

## Batches

| Batch | Content | Status |
|---|---|---|
| dev1 | nudge_compliance, reserve, scale_lambda, bonus_size, blackbox_dev (400 jobs) | done, merged 2026-10-11 |
| dev2 | 4 hard behaviours (no battery declines; late chargers; 30 % compliance; both no declines and 30 %) × 7 arms: B1, (c), (a)(c), (a)(b)(c) IQR, + station bonus, (a) only, station bonus only (280 jobs) | done, merged 2026-10-11 (fingerprint matched) |
| dev3 | Driver-model ceiling (T0 of docs/driver_model_design.md): worlds base / no battery declines / late chargers × 9 arms: B1; (c) time-of-day; legacy, pooled and oracle (a)(b)(d) + time-of-day (c); smart (c) pooled / oracle; pooled / oracle (a)(b)(d) + smart (c) (270 jobs). Batch "dev23" = dev2 + dev3 (550 jobs). | done, merged 2026-10-11 (as part of dev34) |

| dev4 | Coupling the mask (a) to charging, in worlds base / late chargers / no battery declines × 10 arms: B1; (a) only; (a) + mask nudge 12 / 20 / 30 km; (a') soft margin only; (a)(a'); (c) only; (a)(c); (a)(a')(c) + mask nudge 20 km (300 jobs). Batch "dev34" = dev3 + dev4 (570 jobs); notebook default BATCH = "dev34". | done, merged 2026-10-11 (dev34, 570 jobs, fingerprint matched) |

New code (2026-10-11, defaults off, regression identical):
- `addon_mask_nudge`: `BatteryAddOn.forced_nudge` nudges an idle car if the batch mask shut it out of ≥ `mask_nudge_share` of its trips, or if its SOC < `soc_reserve` + `mask_nudge_km` × kWh/km ÷ battery.
- `regular_nudge` = `addon_nudge`, so mask nudges can run without the time-of-day ones.
- (a') `addon_soft_margin` with `soft_margin_width` 0.07.
- dev2 diagnosis of "(a) alone hurts late chargers": idle share +0.14 pt and low-SOC cars at peak +0.32 pt; the batch-share flag rarely fires, hence the SOC rule.

| dev5 | T1, heterogeneous drivers: worlds hetero / hetero + late chargers × 11 arms: B1; (c) time-of-day; smart (c) pooled / oracle; v2 [(a) + mask nudge 30 km, (b) IQR λ 0.5, (c)] with time-of-day nudges (legacy / pooled / oracle), smart nudges (pooled / oracle), hybrid nudges (pooled / oracle) (220 jobs) | done, merged 2026-10-11 (5 shards, fingerprint matched) |

New code for T1 (defaults off, regression identical):
- `driver_hetero`, implemented in `Simulator.threshold_now`:
  - per-decision threshold noise (sd 0.03);
  - per-driver extra threshold U(0, 0.10) in the last 2 h of the shift;
  - per-driver decline margin U(0, 0.10) and sharpness U(0.01, 0.05);
  - unplug target noise (sd 0.05);
  - per-driver nudge compliance `nudge_p` ~ Beta(mean 0.6, κ 2).
- The oracle knows the threshold, the end-of-shift rise, the margin and the sharpness; the pooled model knows the fleet averages.
- `nudge_mode="hybrid"`: smart in the 2 h before each peak, time-of-day level elsewhere.
- Limitation: nudge compliance knowledge has no value in the model yet (no nudge budget or fatigue), so the oracle does not use `nudge_p`.

| dev6 | Phase 2, heterogeneous drivers (main world from now on): **bb7** = module v2 on 7 black boxes B0, B1, B2-F, B2-R, B2, B6, B4c (140 jobs); **levels** = v2 limited to L0/L1 (B1), L0–L2 (B2), L0–L3 (B4c) (120 jobs) | done, merged (dev67) |

| dev7 | **nudge_design** on B1, heterogeneous drivers, 20 arms (200 jobs): v2 default; pre-peak level 40/50/60 % × window 1/1.5/2 h; off-peak level 20/40 %; supply-target nudges (share 80/90 % × SOC 50/60 %); home nudge at shift end (acceptance 30/60 %, and alone). Batch "dev67" = dev6 + dev7 (460 jobs). | done, merged (dev67, 460 jobs, fingerprint matched) |
| dev8 | Schedule refinement on B0, B1, B4c (heterogeneous drivers): v2 default; pre-peak 60/70/80 % for 2 h; 70 % for 2.5 h; target 80 % at SOC 60/70 %; two combinations with off-peak 40 % and home nudge 60 % (300 jobs) | done, merged 2026-10-11 |
| eval1 | **Final evaluation**, full scale, seeds 1000–1019, heterogeneous drivers: 7 black boxes × {black box, + v2.1} + "v2.1 + home" on B1 and B4c (320 jobs) | **done 2026-10-12**, report `outputs/eval_main_report.md` (`scripts/eval_report.py`) |
| ood1 | OOD screening, 1,000 cars, seeds 1000–1009, locked v2.1 on 7 black boxes: demand −20 %, demand +20 %, ports × 0.6 (`port_scale`), harsh (0.20 kWh/km, noisy SOC, nudge compliance mean 0.4) (560 jobs) | done 2026-10-12, reports `outputs/ood_*_report.md` |
| ood2 | Worst OOD (demand +20 %) at full scale, seeds 1000–1019, 7 black boxes × {bb, + v2.1} (280 jobs) | done 2026-10-12, report `outputs/ood_full_demand_plus20_report.md` |
| dev9 | v2.2 development: supply-aware gate on the pre-peak nudges (`nudge_gate` none / idle_share 15 %, 25 % / surplus 0.5, 1.0), on B0, B1, B6, worlds base and demand +20 %, dev seeds 300–309 (360 jobs) | done 2026-10-12, merged (fingerprint matched) |
| eval2 | **Fresh-seed evaluation of locked v2.2** (seeds 2000–2019): `eval2_main` full scale 20 seeds + `eval2_demand_plus20` full scale 10 seeds, 7 black boxes × {bb, + v2.2} (420 jobs) | done 2026-10-13, merged (420/420), reports `outputs/eval2_main_report.md`, `outputs/eval2_demand_plus20_report.md` |

dev7 code (defaults off, regression identical):
- `nudge_mode="target"` uses `BatteryAddOn.target_nudges`:
  - in the 2 h before each peak, nudge just enough idle cars that `target_share` of the cars on shift have SOC ≥ `target_soc` (cars that are charging count at their unplug level);
  - lowest SOC first, near a free charger first;
  - capped by the free ports.
- `addon_home_nudge`: at shift end with SOC < `home_nudge_soc`, P(overnight charge) = p + (1 − p) × `home_nudge_accept`. It reuses the same CRN draw, so it only adds chargers.
- New metric `home_nudges_per_day`.

Phase 2 code (2026-10-11, defaults unchanged, regression identical):
- `b0_greedy` (`GreedyNearest`: ETA cost + its own `solve`, riders in booking order take the nearest free car);
- `b6_value` (`ImmediateValue`: −(P(still there) × fare × (1 − commission) − energy) in thousand VND);
- the simulator uses `policy.solve` when present;
- `addon_level` 0–3:
  - L0: (a) veto after solving, no (b);
  - L1: no forward SOC;
  - L2: current behaviour;
  - L3: `nudge_mode="value"` with `BatteryAddOn.nudge_value`. The time-of-day rule is adjusted by V quartiles among the idle cars: skip if V is in the top quartile unless SOC < 15 %; top up below 60 % off-peak when V is in the bottom quartile.

v2.2 code (defaults off, regression identical):
- `nudge_gate` in `Simulator.nudge_charging` (time-of-day mode, only while the raised pre-peak level applies).
- Cars below `nudge_soc` are always nudged. The extra cars (`nudge_soc` ≤ SOC < pre-peak level) are nudged:
  - `idle_share`: only if idle / on-shift ≥ `gate_idle_share`;
  - `surplus`: at most `gate_surplus_frac` × (idle − waiting riders), lowest SOC first.
- If v2.2 is chosen, it must be evaluated on **fresh seeds 2000+**, because 1000–1019 have been seen.

## OCP1 map demo (started 2026-10-12, user decisions)

- **Option A** (our `evsim` engine + v2.1 on the user's OCP1 data), **40 car charger ports**, heavy map upgrade: side-by-side replay of B1 vs B1 + v2.1 on the same seed.
- Data source: repo https://github.com/ShayNeeo/VRIC_Dispatching_SOC (cloned to the scratchpad). Copied into `data/ocp1/`: `ocp1_graph.json` (1,110 nodes, edges `[u, v, km, speed_kmh]`, pois: 30 stations incl. 10 e-scooter, 4 gates, 3 anchors), `ocp1_params.json`, `ocp1_stations.json`, `fleet_spec.json`, `OCP1.md`, `run_ocp1.py`, `gsm_sim.py`.
- `data/ocp1/ocp1_stations_demo40.json`: mall 8 + depot 8 ports at 60 kW, plus 6 residential sites × 4 at 30 kW (farthest-point spread) = 40.
- **`docs/OCP1_DATA.md`** = the user's SOC-REPORT rewritten to match our simulations. The user said not to follow the original data file. Results are left blank until run.
- The review of the original SOC-REPORT is also recorded:
  - F + B mixes km and VND;
  - the policy lowers profit by 0.5 %;
  - 156 ports for 60 cars is too generous;
  - the baseline uses the private θ_i;
  - SEM taken over correlated days.
- **Built 2026-10-12** (steps 1–5 done):
  - `evsim/ocp1.py`:
    - `NodeRouter`: scipy Dijkstra on the OSM graph minus the lake edges, main component only; cache `data/ocp1/ocp1_router.npz`; cKDTree snapping; points farther than 0.35 km from the network count as outside the map and are reached through the best gate (detour × great-circle outside);
    - `path()` for the replay;
    - demand: 9 anchors, 65 % intra lognormal / 35 % gateway;
    - stations: `ocp1_stations_demo40.json`.
  - Hooks:
    - `geo.set_router("ocp1")`; `road_km` uses `router.road`;
    - config `demand_model`, `ocp1_gateway_share`, `return_to_area`, `log_moves`;
    - simulator `leg_log` / `state_log`;
    - a free car outside the area drives back in.
  - Scenario `SCENARIOS["ocp1_demo"]`: 60 cars, 1,276 bookings/day, 48 h, heterogeneous drivers, CRN.
  - Regression for Hanoi is identical.
  - `scripts/ocp1_demo.py stats|export`.
  - OCP1 result over 20 seeds: **+0.83 ± 0.24 pt service, peak +1.56, profit +6.5k ± 2.1k, 90 % of seeds** (`outputs/ocp1/ocp1_stats.md`, filled into `docs/OCP1_DATA.md` §7).
  - Demo seed **1002**: typical on service, peak service and profit at once. The first pick (1005, by service only) was dropped because its peak service went down.
  - Web: `web/replay.html` + `src/replay.ts` + `src/replay.css`.
    - Two synchronised PixiJS maps on the existing `oceanpark.json` base; cars coloured by SOC, rings for charging / busy; waiting riders; 40-port stations with in use / ports + queue.
    - KPI cards (better / worse colouring), 48 h summary line, chart of charging cars and waiting riders with the peaks shaded, slider, speeds ×30–×600, jump buttons, `?t=` and `&play` URL parameters.
    - `web/vite.config.ts` builds both pages.
  - Demo guide: `docs/DEMO_GUIDE.md`.
- **Demo upgrade (2026-10-12):**
  - `scripts/ocp1_demo.py stats|export` now covers scenes normal / harsh × black boxes B1, B0, B6, B2 (repositioning uses the OCP1 zones in the OCP1 world).
  - Outputs: manifest `outputs/ocp1/ocp1_manifest.json` (copied to `web/public/data`), stats `outputs/ocp1/ocp1_stats_all.md`, runs `outputs/ocp1/ocp1_stats_runs_all.csv`, and 16 replay files `ocp1_replay_<scene>_<bb>_<base|v21>.json` (21 MB).
  - Player: scene and black-box pickers; "+N khách" counter (journeys saved / lost, matched by trip id); stars on the map; 20-seed stats line.
  - Results (20 seeds, 48 h):

    | Scene | B1 | B0 | B6 | B2 |
    |---|---|---|---|---|
    | normal | +0.83 ± 0.24 (+6.5k) | +0.62 ± 0.33 (+6.5k) | +1.01 ± 0.51 (+8.9k) | +0.55 ± 0.39 (+6.1k) |
    | harsh | +0.85 ± 0.36 (+6.1k) | +0.70 ± 0.31 (+7.3k) | +1.11 ± 0.51 (+6.4k) | +0.75 ± 0.33 (+7.9k) |

    Peak service gains are +0.9 to +3.4 pt.
  - Note: about 50–85 journeys a day differ in each direction between the arms (churn); the net is what matters. B1 seed 1002, day 2: +73 / −65.
  - The dev server was reaped once for low memory; do not restart it unless the user asks.
- Original to-do list (done):
  1. node-level router (scipy Dijkstra, predecessors for paths) plugged into `geo` as a router; drop lake edges; exclude the east gate;
  2. OCP1 demand generator (zones, 65 % intra lognormal / 35 % gateway);
  3. scenario `ocp1_demo` (60 cars, 1,276 bookings/day, `driver_hetero`, CRN);
  4. trajectory export (legs with node paths, SOC, station queues);
  5. web split-view player (PixiJS in `web/`) with SOC colours, station queues, KPI timeline and a time slider.

## Driver behaviour tracker (user's idea, 2026-10-11)

- Design: `docs/driver_model_design.md`.
  - Shadow phase → act phase, per driver and per sub-model (S0 / S1 / S2), using prequential scoring, SPRT and Page-Hinkley.
  - Shared latent threshold θ_i for self-charging (M1) and declines (M3), as a grid posterior with an empirical-Bayes prior.
  - Other sub-models: M2 unplug / night charging, M4 nudge compliance, M5 drain / shift.
  - Phase-2 actions: personalised (b) and (d); smart nudges (predicted self-charge falls in a peak); compliance-weighted, congestion-aware nudges; later a rolling charging planner.
  - Roadmap T0 to T5 with decision gates.
- Code for T0:
  - `driver_model` legacy | pooled | oracle;
  - `nudge_mode` time_of_day | smart (+ `nudge_lookahead_h`, `drain_soc_per_h`, `smart_nudge_margin`);
  - `BatteryAddOn.decline_risk`, `self_charge_prob`, `nudge_wanted`;
  - simulator `nudge_charging` calls `policy.nudge_wanted` when `nudge_mode=smart`.
  - Legacy defaults are bit-identical (regression re-checked).
- Gate T0: oracle − pooled ≥ 0.1 pt service or ≥ 2,000 VND/car/day in at least one world; otherwise stop personalisation.

## Next steps (after dev5)

1. Phase 2: black boxes B0 greedy and B6 immediate value; gating by interface level L0–L3 (capability ablation); a dev batch over all 7 black boxes with module v2.
2. Lock module v2 → evaluation batch at full scale (seeds 1000–1019) + OOD.
3. Report.

## Older next-step list

1. Merge and summarise dev2. Question: does the matching side pay off when drivers do not self-manage or ignore nudges?
2. Phase 1–2 code (list under "Not yet built").
3. Batch dev3: capability ablation L0–L3, the new black boxes, the decline model v2.
4. Lock the module → evaluation batch at full scale (seeds 1000–1019) + OOD.
5. Report (Vietnamese) + rewrite the mentor doc as G(F, B).

## 2026-10-12 — Framework figures, paper style (Yue et al., CIKM'24)
- `scripts/make_framework_figs.py` -> `docs/figures/fw_fig1_overview.svg`, `fw_fig2_two_layers.svg`,
  `fw_fig3_architecture.svg`, all three with captions in `framework_figures.html`. One idea per figure:
  1 = the layer wraps the company's matcher across rounds (left: the real OCP1 road graph with cars, riders and
  the 8 demo charger sites at their coordinates); 2 = two layers on two clocks (5 min / 30 s) with
  the worked 3x3 example; 3 = module architecture (inputs bus, locked company modules, outputs, feedback).
- Paper read (D2SN, end-to-end RL with a learned Hold action). Not adopted as a method: it replaces the
  dispatcher (breaks the black-box constraint) and the ceiling run says the remaining gap is mostly charging
  time. Transferable: a battery "hold" (defer a risky pair one round), regime-split parameters by
  demand/supply ratio, and their evaluation layout (results by D&S level x fleet size, hold diagnostics).

## 2026-10-13 — eval2 result (v2.2, fresh seeds 2000–2019)
- **eval2_main** (full scale, 20 seeds): all 7 black boxes non-inferior and superior on both metrics (Holm).
  Goal C: service +0.556 pt (LCB +0.546), profit +8,120 VND/car/day (LCB +7,949); 100 % of seeds gain.
  Per black box service: B0 +0.60, B1 +0.68, B2-F +0.35, B2-R +0.80, B2 +0.39, B6 +0.72, B4c +0.35 pt.
  Peak service +0.61 to +2.22 pt; battery share of declines −15 to −21 pt; run-outs unchanged.
- **eval2_demand_plus20** (full scale, 10 seeds): all 7 pass. Goal C +0.609 pt (LCB +0.595), +11,345 VND (LCB +11,043).
- Caveat: eval2 has no v2.1 arm, so v2.2 vs v2.1 is not a paired comparison. Across different seed sets the
  base-world gain is about the same as v2.1 (eval1: +0.564 pt, +8,264 VND); under demand +20 % v2.2 is a bit
  higher (ood2 v2.1: +0.564 pt, +10.3k). The paired v2.2-vs-v2.1 evidence is dev9 (dev seeds).
- Conclusion: the layer's gain replicates on fresh seeds. v2.1 stays the main locked result; v2.2 is reported as
  the demand-robust variant.
- 2026-10-13: Figure 1 redrawn in English with a top-to-bottom flow per round (candidate pairs -> 1. battery
  layer -> 2. company matcher -> dispatch result) and grey arrows carrying each result into the next round;
  the two OCP1 maps now show round t before / after dispatch. Talk script: `docs/thuyet_trinh_hinh1.md`.
- 2026-10-13 (later): Figure 1 redone as a portrait storyboard (three moments of a day: round t, 20 min later,
  17:00; map left, "1. battery layer -> 2. company matcher -> result" right). The worked example now uses real
  OCP1 positions: pickup distances are road km from the router, routes are real road paths, and the company cost
  is the pickup distance. Result: v3 (10 %) masked from p2 (0.9 km away, 12 km trip, 4 % at the charger); the
  matcher gives p2 to v2 (30 %, ends ~24 %) and v3 takes p3 (1.5 km away, 2 km trip, keeps ~8 %). Figure 2 follows
  the same numbers automatically.
- 2026-10-13 (final layout): Figure 1 = three rows (round t, 20 min later, 17:00), each read left to right:
  OCP1 map (zoomed on the icons) -> candidate pairs -> dispatch rule (1. battery layer, 2. company matcher) ->
  dispatch result, with a grey arrow from each result down to the next row's map. Riders p1/p3 moved slightly so
  icons do not overlap (v3->p3 pickup now 1.3 km; v3 keeps ~9 %).
- 2026-10-13: Figure 1 fixes. Row 2 had a hard-coded 27 % for v2 after a 12 km trip (wrong: 30 % -> ~24 %;
  consumption 0.16 kWh/km on a 37.23 kWh pack = 0.43 %/km). Row 2 is now "15:30, before the peak": a 48 % car,
  above every driver's own threshold (8-25 %), is nudged to top up because 2 cars are spare (gate allows
  int(0.5 x 2) = 1). This shows what self-charging drivers would not do alone.
- 2026-10-13: Figure 1 exported to an editable PowerPoint slide: `scripts/svg_to_pptx.py` (generic converter for
  our SVGs: native shapes, `<g data-name>` -> named groups, `<g data-raster>` maps -> PNG via headless Edge) ->
  `docs/figures/fw_fig1_overview.pptx`. Groups per row: title, map, candidate pairs, battery layer, company
  matcher, dispatch result, result caption, links; plus column headers and legend; icons are sub-groups.
  Checked by exporting the slide through PowerPoint (COM) and with the pptx skill's validate.py (passed).
- 2026-10-13: Figure 3 exported the same way -> `docs/figures/fw_fig3_architecture.pptx` (groups: Tầng ghép,
  Tầng sạc, each module, Đầu vào / Đầu ra pills, the mask -> nudge link, the feedback loop). Checked via PowerPoint.
- 2026-10-13: Figure 3 translated to English (SVG + caption); editable copy `docs/figures/fw_fig3_architecture_en.pptx` (the Vietnamese .pptx was open in PowerPoint, so it was left untouched).
- 2026-10-13: Figure 3 inputs clarified: the shared bus feeds both layers; coloured dots beside each module show which inputs it reads (battery forecast and original cost: fleet + riders; mask: chargers; nudge levels and spare-car gate: context; pick cars: fleet). PPTX: `fw_fig3_architecture_en_v2.pptx` (the _en file was open).
- 2026-10-13: Figure 3 rewritten with every rule spelled out (SOC_after, SOC_charger and mask, decline-risk q, s, lambda, nudge levels with hours, spare-car gate (v2.2), nudge picking rules, mask -> nudge trigger ~18 %, nudge acceptance mean 60 %). svg_to_pptx now keeps SVG subscripts as PowerPoint subscripts.

## 2026-10-13 — Does the "skip cars whose shift ends within 1 h" nudge rule need the true shift end?
- New config `shift_end_info` (exact | noisy | none) + `shift_end_noise_min`; the platform's belief
  `Vehicle.shift_end_est` is used only by that skip rule. Default exact reproduces earlier runs bit for bit
  (checked against the ceiling run, seeds 300-304).
- Experiment `shift_info` (small scale, dev seeds 300-309, B1, heterogeneous drivers), paired vs v2.1 exact:
  - shift end ± 60 min: service −0.02 ± 0.08 pt, peak −0.07 ± 0.15, profit +0.3k ± 1.4k, nudges −36/day;
  - shift end ± 120 min: service +0.00 ± 0.07 pt, peak −0.10 ± 0.17, profit +0.5k ± 1.3k, nudges −108/day;
  - no rule at all: service −0.01 ± 0.05 pt, peak −0.08 ± 0.08, profit −0.1k ± 1.2k, nudges +30/day (+2.6 %);
  - run-outs unchanged in every arm. v2.1's gain over B1 here: +0.48 pt, +1.57 peak, +7.6k.
- Conclusion: the rule is a courtesy to drivers, not a source of the gain. Knowing shift ends is not required;
  every variant stays within noise of the exact one. Optional in the figure.
