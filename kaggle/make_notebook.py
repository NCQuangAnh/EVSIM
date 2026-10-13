"""Write kaggle/evsim_jobs.ipynb: runs one shard of an experiment batch (scripts/experiments.py).

    .venv/Scripts/python kaggle/make_bundle.py      # after any code change, re-upload the bundle
    .venv/Scripts/python kaggle/make_notebook.py

Open the notebook in NSHARDS copies (same BATCH, SHARD = 0 .. NSHARDS-1), Save & Run All each,
download jobs_<batch>_shard<k>.zip from every copy, then on this machine:
    .venv/Scripts/python scripts/run_jobs.py merge path/to/jobs_*_shard*.zip
    .venv/Scripts/python scripts/run_jobs.py summarize --batch <batch>
"""
import json
from pathlib import Path

CELLS = [
    ("markdown", """# EV fleet dispatch – experiment jobs (battery framework)

Runs one shard of an experiment batch from `scripts/experiments.py` on Kaggle CPUs (no GPU needed).

1. Add the dataset with the bundle from `kaggle/make_bundle.py` (`vric.zip` – Kaggle may unpack it –,
   `versions.json`, `fingerprint.json`); `DATASET` below is its path.
2. Settings: Internet **on** (to pin library versions), accelerator **None**.
3. Set `SHARD` (0 … `NSHARDS`-1); keep `BATCH` and `NSHARDS` the same in every copy.
4. *Save Version → Save & Run All*. When done, download `jobs_<BATCH>_shard<SHARD>.zip` from Output.
5. Jobs already finished are skipped, so a copy that stopped can simply be run again."""),
    ("code", """BATCH = "eval2"   # experiment batch in scripts/experiments.py
SHARD = 0         # this copy: 0 .. NSHARDS-1
NSHARDS = 14      # copies running in parallel"""),
    ("code", """import glob, json, os, shutil, subprocess, sys, zipfile

DATASET = "/kaggle/input/datasets/minh12605/evsim-vric"   # where the bundle dataset is mounted
WORK = "/kaggle/working/vric"
# Kaggle unpacks uploaded .zip files, so the code may sit in a folder instead of vric.zip
found = glob.glob(f"{DATASET}/**/versions.json", recursive=True)
if not found:   # the dataset may be mounted elsewhere (other name / version path): search all inputs
    found = glob.glob("/kaggle/input/**/versions.json", recursive=True)
    if found:
        DATASET = os.path.dirname(found[0])
        while os.path.dirname(DATASET) != "/kaggle/input" and not glob.glob(f"{DATASET}/**/vric.zip", recursive=True)                 and not glob.glob(f"{DATASET}/**/run_baseline.py", recursive=True):
            DATASET = os.path.dirname(DATASET)
if not found:
    print("Inputs attached to this notebook:")
    for root, dirs, files in os.walk("/kaggle/input"):
        if root.count(os.sep) <= 5:
            print(" ", root, files[:5])
    raise FileNotFoundError("bundle not found: add the dataset with versions.json / vric.zip in Input (right panel)")
BUNDLE = os.path.dirname(found[0])
print("dataset:", DATASET)
zips = glob.glob(f"{DATASET}/**/vric.zip", recursive=True)
if zips:
    os.makedirs(WORK, exist_ok=True)
    zipfile.ZipFile(zips[0]).extractall(WORK)
else:
    code_root = os.path.dirname(glob.glob(f"{DATASET}/**/run_baseline.py", recursive=True)[0])
    shutil.copytree(code_root, WORK, dirs_exist_ok=True)   # the input folder is read-only
for need in ["run_baseline.py", "evsim/simulator.py", "evsim/battery.py", "scripts/run_jobs.py",
             "scripts/experiments.py", "data/road_cells.npz", "data/stations_google.csv",
             "data/didi_values_hanoi_full.npz", "data/reject_curve.json"]:
    assert os.path.exists(f"{WORK}/{need}"), f"missing {need} in the dataset (re-run kaggle/make_bundle.py)"
ver = json.load(open(f"{BUNDLE}/versions.json"))
print("bundle", BUNDLE, "| local versions", ver, "| Kaggle python", sys.version.split()[0], "| CPUs", os.cpu_count())

# same numpy/scipy/pandas as the machine that made the bundle, so seeds give the same inputs
subprocess.run([sys.executable, "-m", "pip", "install", "-q", f"numpy=={ver['numpy']}",
                f"scipy=={ver['scipy']}", f"pandas=={ver['pandas']}", "tabulate"], check=True)"""),
    ("code", """# reproducibility check: tiny runs must match the ones made on the local machine.
# All arms of a batch run here with the same pinned libraries, so a mismatch does not spoil
# the pairing inside the batch; it only means these results must not be mixed with local runs.
check = r'''
import dataclasses, json, sys
sys.path.insert(0, ".")
from evsim.battery import POLICIES
from evsim.config import SCENARIOS, Config
from evsim.metrics import summarize
from evsim.simulator import Simulator
ref = json.load(open(sys.argv[1]))
out = {}
for name, case in ref["cases"].items():
    cfg = dataclasses.replace(Config(), seed=ref["seed"], **{**SCENARIOS[ref["scenario"]], **case["overrides"]})
    got = summarize(Simulator(cfg, POLICIES[case["policy"]](cfg)).run())[0]
    out[name] = {k: round(float(got[k]), 6) for k in case["metrics"]}
print(json.dumps(out))
'''
res = subprocess.run([sys.executable, "-c", check, f"{BUNDLE}/fingerprint.json"], cwd=WORK,
                     capture_output=True, text=True)
print(res.stderr[-2000:])
got = json.loads(res.stdout.strip().splitlines()[-1])
want = {k: v["metrics"] for k, v in json.load(open(f"{BUNDLE}/fingerprint.json"))["cases"].items()}
MATCH = got == want
print("fingerprint matches the local machine:", MATCH)
if not MATCH:
    print("local:", want); print("kaggle:", got)"""),
    ("code", """cmd = [sys.executable, "-u", "-W", "ignore", "scripts/run_jobs.py", "run", "--batch", BATCH,
       "--shard", str(SHARD), "--nshards", str(NSHARDS), "--jobs", str(os.cpu_count())]
print(" ".join(cmd))
p = subprocess.Popen(cmd, cwd=WORK, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
for line in p.stdout:
    print(line, end="")
assert p.wait() == 0, "jobs failed"
"""),
    ("code", """# package this shard's results for download
out = f"/kaggle/working/jobs_{BATCH}_shard{SHARD}.zip"
n = 0
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in glob.glob(f"{WORK}/outputs/jobs/**/*.json", recursive=True):
        z.write(f, os.path.relpath(f, WORK)); n += 1
    z.writestr("kaggle_meta.json", json.dumps({"batch": BATCH, "shard": SHARD, "nshards": NSHARDS,
                                               "fingerprint_match": MATCH, "python": sys.version.split()[0]}))
print("saved", out, n, "job files,", round(os.path.getsize(out) / 1e6, 2), "MB")"""),
]


def main():
    nb = {"nbformat": 4, "nbformat_minor": 5,
          "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                       "language_info": {"name": "python"}},
          "cells": [{"cell_type": t, "metadata": {}, "source": src.splitlines(keepends=True),
                     **({"outputs": [], "execution_count": None} if t == "code" else {})}
                    for t, src in CELLS]}
    out = Path(__file__).resolve().parent / "evsim_jobs.ipynb"
    out.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
