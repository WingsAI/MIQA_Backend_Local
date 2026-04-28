"""CT v2: pseudo-volumes formados pela ordem numérica dos arquivos no
diretório original (raw), agrupados em janelas de N slices consecutivos.

Como o dataset tem metadados anonimizados, reconstruímos volumes usando
o nome de arquivo numérico como proxy de ordem aquisitiva.

Saída: miqa/results/ct_v2_metrics.csv  (1 linha por pseudo-volume)
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd
import pydicom

from miqa.metrics.ct_v2 import slice_consistency

ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "ct_raw_stroke"
CSV_OUT = ROOT / "results" / "ct_v2_metrics.csv"

WINDOW = 20  # slices por pseudo-volume
STRIDE = 20  # não-sobreposto
MAX_DCMS_PER_DIR = 200  # limita quantos DICOMs lemos por diretório (vai a 10 volumes/pasta)


def load_hu(path: Path) -> np.ndarray | None:
    try:
        ds = pydicom.dcmread(path)
        arr = ds.pixel_array.astype(np.float32)
        slope = float(ds.get("RescaleSlope", 1.0))
        intercept = float(ds.get("RescaleIntercept", 0.0))
        return arr * slope + intercept
    except Exception:
        return None


def numeric_key(p: Path) -> int:
    try:
        return int(p.stem)
    except ValueError:
        return -1


def main():
    # encontra dirs com .dcm
    dicom_dirs = set()
    for f in RAW.rglob("*.dcm"):
        dicom_dirs.add(f.parent)
    dicom_dirs = sorted(dicom_dirs)
    print(f"Encontrados {len(dicom_dirs)} diretórios com DICOMs")

    rows = []
    for d in dicom_dirs:
        files = sorted([f for f in d.glob("*.dcm")], key=numeric_key)
        files = files[:MAX_DCMS_PER_DIR]
        n_vol = max(0, (len(files) - WINDOW) // STRIDE + 1)
        print(f"  {d.name}: {len(files)} slices → {n_vol} pseudo-volumes")
        for v_idx in range(n_vol):
            window = files[v_idx*STRIDE : v_idx*STRIDE + WINDOW]
            slices = []
            shape_first = None
            for fp in window:
                hu = load_hu(fp)
                if hu is None: continue
                if shape_first is None:
                    shape_first = hu.shape
                if hu.shape != shape_first:
                    continue  # ignora slices de tamanho diferente
                slices.append(hu)
            if len(slices) < 5:
                continue
            r = slice_consistency(slices)
            rows.append({
                "dir": d.name,
                "vol_idx": v_idx,
                "first_file": window[0].name,
                "last_file": window[-1].name,
                **r,
            })

    df = pd.DataFrame(rows)
    df.to_csv(CSV_OUT, index=False)
    print(f"\nCSV: {CSV_OUT}  ({len(df)} pseudo-volumes)")
    if len(df):
        for c in ("mean_hu_drift", "air_sigma_cov", "slice_corr", "anomaly_pct"):
            s = df[c].dropna()
            if len(s):
                print(f"  {c}  med={s.median():.3f}  p25={s.quantile(.25):.3f}  p75={s.quantile(.75):.3f}")


if __name__ == "__main__":
    main()
