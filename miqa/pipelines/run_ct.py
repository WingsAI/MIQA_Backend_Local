"""Pipeline CT: lê DICOMs em miqa/data/ct_subset/, aplica RescaleSlope/Intercept
para converter para HU reais, calcula métricas universal+ct.

Uso: python -m miqa.pipelines.run_ct
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pydicom

from miqa.metrics.universal import run_all as run_universal
from miqa.metrics.ct import run_all_ct

ROOT = Path(__file__).parent.parent
SUBSET = ROOT / "data" / "ct_subset"
RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)


def load_ct(path: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    """Lê DICOM CT, retorna (img_hu, img_norm01, meta).
    img_hu: float32 em Hounsfield Units (para métricas CT)
    img_norm01: float32 em [0,1] janelado p/ tecidos moles (para universais e display)
    """
    ds = pydicom.dcmread(path)
    arr = ds.pixel_array.astype(np.float32)
    slope = float(ds.get("RescaleSlope", 1.0))
    intercept = float(ds.get("RescaleIntercept", 0.0))
    hu = arr * slope + intercept
    # window/level típico de tecidos moles: WL=40, WW=400 → -160 a +240 HU → [0,1]
    wl, ww = 40.0, 400.0
    lo, hi = wl - ww / 2, wl + ww / 2
    norm = np.clip((hu - lo) / (hi - lo), 0, 1).astype(np.float32)
    meta = {
        "file": path.name,
        "shape": str(arr.shape),
        "fmt": "dcm",
        "rescale_slope": slope,
        "rescale_intercept": intercept,
        "hu_min": float(hu.min()),
        "hu_max": float(hu.max()),
        "modality": ds.get("Modality", "?"),
    }
    return hu.astype(np.float32), norm, meta


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
        raise SystemExit(f"sem .dcm em {SUBSET} — rode `python -m miqa.data.download_ct` antes")

    rows = []
    print(f"processando {len(files)} arquivos CT")
    skipped = 0
    for f in files:
        try:
            hu, norm, meta = load_ct(f)
        except Exception as e:
            skipped += 1
            print(f"  SKIP {f.name}: {e}")
            continue
        u = run_universal(norm)         # universais no [0,1]
        ct = run_all_ct(hu)              # CT-específicas em HU
        row = {**meta, **flatten({"u": u}), **flatten({"ct": ct})}
        rows.append(row)
        if len(rows) % 50 == 0:
            print(f"  ... {len(rows)} processadas")

    df = pd.DataFrame(rows)
    csv = RESULTS / "ct_quality.csv"
    df.to_csv(csv, index=False)
    print(f"\nCSV: {csv}  ({len(df)} linhas, {len(df.columns)} colunas) — skipped: {skipped}")


if __name__ == "__main__":
    main()
