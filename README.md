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

## Data notes

Road networks and charger locations come from OpenStreetMap (© OpenStreetMap contributors, ODbL). Google
Places data is not included; `scripts/fetch_google_stations.py` rebuilds it with your own API key
(`GOOGLE_MAPS_API_KEY`).
