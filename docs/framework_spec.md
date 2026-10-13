# Battery framework: contract between the battery layer and a dispatch rule

*Draft, 2026-10-11. Status: design. Numbers quoted are simulation results.*

## 1. Idea

The battery layer is not a new dispatcher. It sits around an existing dispatch rule (the black box) and asks that rule for a small set of interfaces. The more interfaces a dispatch rule exposes, the more the battery layer can do. This gives two things a report can defend:

1. **A clear requirement list for the platform.** It states what a dispatch rule must expose for the battery layer to work, and what is gained at each level.
2. **A testable claim.** The gain should grow with the interface level. This is tested by running the same dispatch rule at each level (a capability ablation).

## 2. Interface levels

| Level | What the dispatch rule exposes | What the battery layer can do | Black boxes in the simulator |
|---|---|---|---|
| **L0: assignments only** | The final (car, rider) pairs, before the offer is sent | Veto an unsafe pair before the offer is sent; the rider goes back to the next round. Charge nudges for idle cars. | Any, including greedy nearest-car |
| **L1: score matrix** | The cost or score F_ij for every candidate pair, and the solver accepts a modified matrix G and a mask | (a) feasibility mask, (b) decline-risk term G(F, B), on top of L0 | B0 greedy (if its scores are exposed), B1, B2, B6, B4c |
| **L2: candidate and state hooks** | For each candidate: when and where it becomes free (forward dispatch), and trip distance/destination for each rider. Accepts a list of cars withdrawn from matching (sent to charge). | Exact SOC at availability for forward candidates; coordinate nudges with matching (do not offer a ride to a car just told to charge, and vice versa) | B2, B4c |
| **L3: value or forecast** | A value of a car's position and time (V of DiDi), or the demand forecast used by repositioning | Time charging by opportunity cost: charge when the car's value on the road is low, instead of fixed SOC thresholds by hour. Keep repositioning targets reachable with the car's SOC. | B4c (V), B2 (forecast) |

Interfaces the platform must provide at every level:

- **SOC telemetry**: frequency and accuracy. The simulator ablation shows noise of sd 5 %, 5-minute reports or 25 % bands are enough.
- **Energy model**: kWh per km, battery size by vehicle type.
- **Charger list**: with live occupancy if available (V-Green app).
- **Driver response data**: offer logs with accept/decline and SOC (to fit the decline model), and nudge follow-up logs (to estimate compliance).

## 3. What the battery layer guarantees to the dispatch rule

1. **Neutral when the battery is irrelevant.** If every car has high SOC, G = F and the dispatch decisions are unchanged.
2. **Respects the ranking.** G increases with F, so it never prefers a pair the black box ranks worse unless the battery risk differs.
3. **Scale invariant.** If F is replaced by aF + b (a > 0), the assignments do not change. The penalty is scaled by a robust spread of F (IQR of the feasible entries), so λ has no unit. Verified by a unit test, not only by simulation.
4. **Hard constraints only for safety.** A pair is forbidden only when the car could not reach any charger after the trip. Low but safe margins are a soft penalty.
5. **Nudges are suggestions.** A driver may ignore them (`nudge_accept_p`). The driver still chooses the station.

## 4. Components (v2, to be built in phase 1)

| | Component | Form | Level needed |
|---|---|---|---|
| (a) | Safety mask | Forbid only if SOC after the trip < energy to the nearest charger + safety reserve; the reserve is a sensitivity parameter | L1 (L0: veto) |
| (a') | Low-margin penalty | Soft penalty for pairs that are safe but leave less than a comfort reserve | L1 |
| (b) | Decline risk | q_pin = p̂(decline \| SOC after, pickup km, trip km) − p̂(same pair at high SOC), logistic model calibrated on held-out logs; G = F + λ · s_F · q_pin | L1 |
| (c) | Charge nudges | Idle cars below a time-of-day SOC level, skipped when nearby chargers are congested; driver follows with probability p | L0 |
| (c') | Value-timed charging | Nudge when the expected loss of being off-road is lowest, from V or the demand forecast | L3 |

## 5. Capability ablation (claim to test)

Run one dispatch rule that supports every level (B4c), with the battery layer limited to L0, L1, L2 and L3. Expected: gain(L0) ≤ gain(L1) ≤ gain(L2) ≤ gain(L3). Repeat on B2 up to L2. If the ordering fails, the requirement list in section 2 must be revised.

## 6. Result of the capability ablation (dev6, 2026-10-11, simulation)

The claim in section 5 did **not** hold: L0 ≈ L1 ≈ L2, and L3 (value-timed nudges) was slightly worse. Almost all of the gain comes from the charging action (c), which needs only L0. Revised requirement list:

- **minimum (enough for the full measured gain):** the solved assignments before offers are sent (to veto unsafe pairs), SOC telemetry, and a channel to send charge nudges;
- higher levels are optional; in the simulator they did not add value.
