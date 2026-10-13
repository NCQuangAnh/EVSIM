# EVSIM: battery-aware dispatch for an electric ride-hailing fleet

Simulator and battery layer built for the VRIC × GSM internship (group 2). The battery layer wraps any
black-box matcher without changing it: every 30 s it removes rider–car pairs that would leave a car unable
to reach a charger (5 % reserve) and adds a decline-risk penalty to the company's cost; every 5 min it
recommends charging to idle cars by time of day (70 % before the peaks, 15 % during them, 30 % otherwise),
only when cars are spare (v2.2).

## Layout

| Path | What |
|---|---|
| `evsim/` | simulator (`simulator.py`), battery layer (`battery.py`), black-box dispatchers (`dispatch.py`), config and scenarios (`config.py`), Ocean Park 1 road router (`ocp1.py`), metrics |
| `scripts/` | experiment catalogue (`experiments.py`), job runner (`run_jobs.py`), evaluation report (`eval_report.py`), OCP1 demo export, figure scripts |
| `kaggle/` | bundle and notebook builders for running experiment batches on Kaggle |
| `web/` | PixiJS replay of the Ocean Park 1 demo (`npm install && npm run dev`, page `replay.html`) |
| `data/` | road and charger data used by the simulator (OpenStreetMap-derived), Ocean Park 1 graph and demo chargers |
| `docs/` | protocol, framework spec, work log, demo guide |

## Quick start

```bash
python -m venv .venv && .venv/Scripts/pip install numpy scipy pandas
.venv/Scripts/python scripts/run_jobs.py run --exp shift_info --jobs 4      # a small experiment
.venv/Scripts/python scripts/run_jobs.py summarize --exp shift_info
```

The evaluation protocol (seeds, non-inferiority margins, Holm correction) is in `docs/protocol.md`; results and
decisions are logged in `docs/WORKLOG.md`.

## Web demo: Ocean Park 1 side-by-side replay

Two maps of the same area (Ocean Park 1, Hanoi) with the same 60 cars, drivers and riders (same seed, common
random numbers): on the left the company-style matcher alone, on the right the same matcher with the battery
layer. The replay files are already in `web/public/data/`, so no Python run is needed to watch it.

Requirements: Node.js 20 or newer.

```bash
cd web
npm install
npm run dev
```

Then open:

- http://localhost:5173/replay.html: the side-by-side replay (main demo);
- http://localhost:5173/: the Ocean Park 1 map explorer.

URL options for `replay.html`:

| Option | Effect | Example |
|---|---|---|
| `t=<hour>` | start at that time of day | `?t=6.5` opens at 06:30 |
| `play` | start playing at once | `?t=5&play` |
| `scene=normal\|harsh` | scenario; harsh = 0.20 kWh/km, noisy SOC, 40 % of recommendations followed | `&scene=harsh` |
| `bb=b1\|b0\|b6\|b2` | black-box matcher: B1 company-style (default), B0 greedy, B6 trip value, B2 forward + repositioning | `&bb=b6` |

The "Kết quả" button opens a results table: pick a scenario, a black box and any subset of the 20 seeds, and get
the mean of each metric with and without the battery layer plus the relative difference (green / red = better /
worse with a 95 % confidence interval excluding 0; hover for the absolute difference). Data:
`web/public/data/ocp1_runs.json`, written by `scripts/ocp1_demo.py stats`.

Controls: space or ▶ to play / pause; the time bar to seek; speed ×30 to ×600; jump buttons for 05:00, 06:30,
07:30, 16:00 and 17:30; mouse wheel to zoom both maps, drag to pan, double-click to fit. The "+N riders" counter
pairs the same booking on both sides: a green star marks a trip served only on the right, a red star one served
only on the left. Car colour is the state of charge; a blue outline means going to, waiting at or using a charger.

To rebuild the replay data after changing the simulator (Python environment with numpy, scipy, pandas):

```bash
.venv/Scripts/python -W ignore scripts/ocp1_demo.py stats --jobs 4    # 20 seeds x 2 scenarios x 4 black boxes
.venv/Scripts/python -W ignore scripts/ocp1_demo.py export --jobs 4   # 16 replay files + manifest -> web/public/data/
```

For a machine without Node at demo time, build once with `npm run build` and serve `web/dist/` with any static
web server (for example `npx vite preview`). The talk track and expected questions are in `docs/DEMO_GUIDE.md`
(Vietnamese).

## Data notes

Road networks and charger locations come from OpenStreetMap (© OpenStreetMap contributors, ODbL). Google
Places data is not included; `scripts/fetch_google_stations.py` rebuilds it with your own API key
(`GOOGLE_MAPS_API_KEY`).
