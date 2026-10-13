# Evaluation protocol for the battery framework

*Draft, 2026-10-11. To be locked before phase 4. Changes after the evaluation seeds have been looked at invalidate them as a final test.*

## Seeds

| Role | Seeds | Used for |
|---|---|---|
| Fit | 200–201 (more if the decline model is unstable) | Decline model, DiDi values V |
| Tuning (old) | 100–101 | λ of module v1 only |
| Development | 300–319 | Choosing the module version, λ, nudge thresholds, every other parameter |
| Evaluation | 1000–1019 | Final run of the locked configuration only |
| Reported earlier | 0–4 | Results of module v1 (kept as history, not used for v2 decisions) |

All runs use common random numbers (`crn=True`): exogenous inputs (demand, vehicles, initial SOC, shifts) are fixed per seed, and every in-run random draw is tied to its entity (vehicle, request, day), so paired policies meet the same luck.

## Margins (non-inferiority), set 2026-10-11

| Metric | Largest acceptable loss | Note |
|---|---|---|
| Service level | 0.1 percentage point | ≈ 1 journey per 1,000 bookings |
| Profit per car per day, inventory-adjusted | 2,000 VND | ≈ 0.15 % of the baseline; uses `profit_adj_per_vehicle_day_vnd` (energy left in batteries valued at the grid price) |

The margins are operational, not statistical. If the development runs show that 20 evaluation seeds cannot reach the needed precision, the number of seeds is raised or the result is reported as inconclusive. The margins are not widened.

## Decision rules

For each black box k and evaluation seed s: Δ_k,s = metric(black box + layer) − metric(black box).

- **Goal B (no black box is made worse):** for every k, the one-sided 95 % lower confidence bound of mean Δ_k is above −margin, for both metrics. Simultaneous claims across all black boxes and both metrics use the Holm correction.
- **Goal C (average gain):** Δ̄_s = (1/K) Σ_k Δ_k,s with equal weights; the gain is significant when the lower confidence bound of mean Δ̄ is above 0. Service level and profit are reported separately; a claim that both improve needs both.
- Report the mean, the 95 % interval and the share of seeds that improve.

## Black boxes

| Code | Policy | Role |
|---|---|---|
| B0 | Greedy nearest car / ETA, no Hungarian | Different matching structure |
| B1 | `gsm_baseline` | GSM proxy, main reference |
| B2 | `gsm_fwd_repo` | Forward dispatch + repositioning |
| B2-F | `gsm_fwd` | Forward dispatch only |
| B2-R | `gsm_repo` | Repositioning only |
| B6 | Expected immediate value: −(P(completed) × fare − operating cost), no future value | Economic score without V |
| B4c | `b4_didi` + `didi_cancel_aware` | Future value (V learned from B2 runs) |

Notes to report: B2/B4c filter forward candidates by the driver's own charging threshold and repositioning by SOC, so the candidate rules are not battery-free even though their cost functions are. V of B4c is learned from B2 trajectories on fit seeds and fixed during evaluation.

## Scenarios

- Main: `hanoi_full` at full scale (5,080 cars), 72 h.
- Out of distribution, screened at 1,000 cars: demand ±20 % with a sharper peak; fewer charger ports / higher private occupancy; higher consumption (0.18 kWh/km) with noisy SOC and nudge compliance below 1. The worst of these is repeated at full scale if resources allow. Small-scale OOD results are reported as screening, not as proof of non-inferiority at full scale.

## Locked configuration (2026-10-11, after development batches dev1–dev8)

- **Main world:** `hanoi_full` with heterogeneous drivers (`driver_hetero`), CRN, `charge_before_home`, 72 h, full scale (5,080 cars).
- **Module v2.1:**
  - (a) safety mask, plus a nudge when SOC cannot cover a 30 km trip;
  - (b) decline risk with the legacy curve, IQR-scaled, λ = 0.5;
  - (c) time-of-day nudges: **70 % in the 2.5 h before each peak** (4:30–7:00, 14:30–17:00), 15 % in peaks, 30 % otherwise.
  - Interface level L2. It is the same as L0 in development; L2 is kept because it is what the code ran.
- **Variant "+ home"** (B1, B4c only): end-of-shift home-charging nudge, acceptance 60 %. This is an assumption and is reported separately.
- **Evaluation:** 7 black boxes (B0, B1, B2-F, B2-R, B2, B6, B4c) × {black box, + v2.1}, seeds 1000–1019, batch `eval1` (320 jobs).
- **Decision rules:** as above (goal B per black box with Holm; goal C as the equal-weight average).
- **Selection bias note:** the schedule was the best of 9 on dev seeds 300–309. The evaluation seeds were never used for any choice.

## Locked v2.2 (2026-10-12, after dev9)

- **Why v2.2 exists:** OOD screening (`ood1`) found one failure. With demand +20 %, B0 + v2.1 lost 1.2k VND profit, LCB −2.6k, below the 2,000 VND margin. Pulling cars to charge before the peaks costs trips when supply is short.
- **v2.2 = v2.1 + supply-aware gate.** Cars below 30 % are always nudged. The extra pre-peak nudges (30–70 %) are limited to 0.5 × (idle cars − waiting riders) per round, lowest SOC first (`nudge_gate="surplus"`, `gate_surplus_frac=0.5`).
- **Selection:** best of 4 gates on dev seeds 300–309 (`dev9`, B0 / B1 / B6, base world and demand +20 %). Equal or better than v2.1 in the base world; clearly better with demand +20 %:
  - B0: +0.18 vs +0.10 pt, profit +3.1k vs +0.9k;
  - B1: +0.24 vs +0.17 pt;
  - B6: +0.24 vs +0.13 pt.
- **Evaluation `eval2`, on fresh seeds 2000–2019.** Seeds 1000–1019 were already seen in `eval1` and `ood1`.
  - Main world: 20 seeds.
  - Demand +20 %: 10 seeds.
  - Both at full scale, 7 black boxes × {black box, + v2.2}, 420 jobs.
  - Same decision rules as above.
