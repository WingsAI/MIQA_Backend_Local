"""Pipeline US: lê imagens em miqa/data/us_subset/, calcula universal+us,
escreve CSV em miqa/results/us_quality.csv.

Uso: python -m miqa.pipelines.run_us
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd
import cv2

from miqa.metrics.universal import run_all as run_universal
from miqa.metrics.us import run_all_us

ROOT = Path(__file__).parent.parent
SUBSET = ROOT / "data" / "us_subset"
RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)


def load_us(path: Path) -> tuple[np.ndarray, dict]:
    arr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if arr is None:
        raise ValueError(f"cv2.imread falhou em {path}")
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    arr = arr.astype(np.float32)
    a, b = float(arr.min()), float(arr.max())
    img = (arr - a) / max(b - a, 1e-9)
    return img.astype(np.float32), {
        "file": path.name, "shape": str(arr.shape),
        "fmt": path.suffix[1:], "raw_min": a, "raw_max": b,
    }


def flatten(d: dict, parent: str = "") -> dict:
    out = {}
    for k, v in d.items():
        key = f"{parent}.{k}" if parent else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        elif isinstance(v, (tuple, list)):
            out[key] = json.dumps(v)
        else:
            out[key] = v
    return out


def main():
    files = []
    for pat in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
        files.extend(SUBSET.glob(pat))
    files = sorted(files)
    if not files:
        raise SystemExit(f"sem imagens em {SUBSET} — rode `python -m miqa.data.download_us` antes")

    rows = []
    print(f"processando {len(files)} arquivos US")
    for f in files:
        try:
            img, meta = load_us(f)
        except Exception as e:
            print(f"  SKIP {f.name}: {e}")
            continue
        u = run_universal(img)
        us = run_all_us(img)
        row = {**meta, **flatten({"u": u}), **flatten({"us": us})}
        rows.append(row)
        print(f"  {f.name[:30]:30s}  speckle={us['speckle_snr']['value']:.2f}"
              f"  shadow={us['shadowing']['value']:.2f}  DoP={us['depth_of_penetration']['value']:.2f}"
              f"  gain={us['gain']['flag']}")

    df = pd.DataFrame(rows)
    csv_path = RESULTS / "us_quality.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nCSV: {csv_path}  ({len(df)} linhas, {len(df.columns)} colunas)")


if __name__ == "__main__":
    main()
