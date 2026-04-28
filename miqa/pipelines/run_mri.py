"""Pipeline MRI: lê DICOMs em miqa/data/mri_subset/, calcula universal+mri,
escreve CSV em miqa/results/mri_quality.csv.

Uso: python -m miqa.pipelines.run_mri
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pydicom

from miqa.metrics.universal import run_all as run_universal
from miqa.metrics.mri import run_all_mri

ROOT = Path(__file__).parent.parent
SUBSET = ROOT / "data" / "mri_subset"
RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)


def load_mri(path: Path) -> tuple[np.ndarray, dict]:
    ds = pydicom.dcmread(path)
    arr = ds.pixel_array.astype(np.float32)
    if arr.ndim == 3:
        arr = arr[arr.shape[0] // 2]  # se multi-frame, pega slice central
    a, b = float(arr.min()), float(arr.max())
    img = (arr - a) / max(b - a, 1e-9)
    meta = {
        "file": path.name,
        "shape": str(arr.shape),
        "fmt": "dcm",
        "raw_min": a,
        "raw_max": b,
        "modality": str(ds.get("Modality", "?")),
    }
    return img.astype(np.float32), meta


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
    files = sorted(SUBSET.glob("*.dcm"))
    if not files:
        raise SystemExit(f"sem .dcm em {SUBSET}")

    rows = []
    skipped = 0
    print(f"processando {len(files)} arquivos MRI")
    for f in files:
        try:
            img, meta = load_mri(f)
        except Exception as e:
            skipped += 1
            print(f"  SKIP {f.name}: {e}")
            continue
        u = run_universal(img)
        m = run_all_mri(img)
        row = {**meta, **flatten({"u": u}), **flatten({"mri": m})}
        rows.append(row)
        if len(rows) % 25 == 0:
            print(f"  {len(rows)}/{len(files)}")

    df = pd.DataFrame(rows)
    csv = RESULTS / "mri_quality.csv"
    df.to_csv(csv, index=False)
    print(f"\nCSV: {csv}  ({len(df)} linhas) — skipped: {skipped}")
    for c in ("mri.nema_snr.value", "mri.ghosting.value",
              "mri.bias_field.value", "mri.motion_hf.value"):
        if c in df.columns:
            s = df[c].dropna()
            if len(s):
                print(f"  {c}  med={s.median():.3f}  p25={s.quantile(.25):.3f}  p75={s.quantile(.75):.3f}  válido={len(s)}/{len(df)}")


if __name__ == "__main__":
    main()
