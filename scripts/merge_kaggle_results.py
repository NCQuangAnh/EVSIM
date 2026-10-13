"""Merge results downloaded from the Kaggle ablation notebooks into outputs/.

    .venv/Scripts/python scripts/merge_kaggle_results.py path/to/results_full_shard*.zip
    .venv/Scripts/python scripts/run_ablation.py --stage full --summarize-only

Copies each run folder (skipping ones already present) and appends the shard's rows to the
run registry outputs/runs/index.csv without duplicating (run_id, policy, seed).
"""
import io
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def main(paths):
    index_path = ROOT / "outputs" / "runs" / "index.csv"
    index = pd.read_csv(index_path) if index_path.exists() else pd.DataFrame()
    for p in paths:
        with zipfile.ZipFile(p) as z:
            meta = json.loads(z.read("kaggle_meta.json"))
            new = 0
            for name in z.namelist():
                if name == "kaggle_meta.json" or name.endswith("runs/index.csv"):
                    continue
                dest = ROOT / name
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(z.read(name))
                    new += 1
            idx_name = "outputs/runs/index.csv"
            if idx_name in z.namelist():
                rows = pd.read_csv(io.BytesIO(z.read(idx_name)))
                index = pd.concat([index, rows]).drop_duplicates(["run_id", "policy", "seed"], keep="first")
        print(f"{p}: stage {meta['stage']} shard {meta['shard']}/{meta['nshards']}, "
              f"reuse_ok={meta['reuse_ok']}, {new} new files")
    index.to_csv(index_path, index=False)
    print(f"run registry now has {len(index)} rows")


if __name__ == "__main__":
    main(sys.argv[1:])
