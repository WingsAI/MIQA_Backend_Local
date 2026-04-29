"""Pipeline anatomy-aware unificado.

Detecta anatomia de cada imagem e roda métricas específicas para aquele contexto.
Mantém compatibilidade com pipelines antigos — este é um layer adicional.

Uso:
    python -m miqa.pipelines.run_anatomy_aware --modality all

Saída: miqa/results/anatomy_aware_metrics.csv
"""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pydicom

from miqa.anatomy import detect_anatomy, run_anatomy_aware_metrics, AnatomicalContext
from miqa.metrics.universal_v2 import run_all_v2

ROOT = Path(__file__).parent.parent
RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)


def load_image(path: Path, modality: str) -> tuple[np.ndarray, dict, np.ndarray | None]:
    """Carrega imagem e retorna (img_norm, meta, hu_array).
    hu_array é None exceto para CT."""
    if modality == "ct":
        ds = pydicom.dcmread(path)
        arr = ds.pixel_array.astype(np.float32)
        slope = float(ds.get("RescaleSlope", 1.0))
        intercept = float(ds.get("RescaleIntercept", 0.0))
        hu = arr * slope + intercept
        # Normaliza para [0,1] com janela de tecido
        wl, ww = 40.0, 400.0
        lo, hi = wl - ww/2, wl + ww/2
        norm = np.clip((hu - lo) / (hi - lo), 0, 1)
        meta = {
            "file": path.name,
            "modality": modality,
            "shape": str(arr.shape),
            "hu_range": f"{hu.min():.0f},{hu.max():.0f}",
        }
        return norm.astype(np.float32), meta, hu
    else:
        if modality in ("rx", "us"):
            import cv2
            arr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if arr is None:
                ds = pydicom.dcmread(path)
                arr = ds.pixel_array.astype(np.float32)
            if arr.ndim == 3:
                arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        else:  # mri
            ds = pydicom.dcmread(path)
            arr = ds.pixel_array.astype(np.float32)
            if arr.ndim == 3:
                arr = arr[arr.shape[0] // 2]
        a, b = float(arr.min()), float(arr.max())
        norm = (arr - a) / max(b - a, 1e-9)
        meta = {
            "file": path.name,
            "modality": modality,
            "shape": str(arr.shape),
        }
        return norm.astype(np.float32), meta, None


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


def is_real(p: Path) -> bool:
    return not p.name.startswith("._")


SUBSETS = {
    "rx":  (ROOT / "data" / "rx_subset",  "*"),
    "us":  (ROOT / "data" / "us_subset",  "*"),
    "ct":  (ROOT / "data" / "ct_subset",  "*.dcm"),
    "mri": (ROOT / "data" / "mri_subset", "*.dcm"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modality", choices=["rx", "us", "ct", "mri", "all"], default="all")
    args = ap.parse_args()

    mods = ["rx", "us", "ct", "mri"] if args.modality == "all" else [args.modality]
    rows = []

    for mod in mods:
        subset_dir, pattern = SUBSETS[mod]
        files = [f for f in sorted(subset_dir.glob(pattern)) if is_real(f)]
        print(f"\n=== {mod.upper()} (n={len(files)}) ===")
        t0 = time.time()

        for i, f in enumerate(files, 1):
            try:
                img_norm, meta, hu = load_image(f, mod)
            except Exception as e:
                print(f"  SKIP {f.name}: {e}")
                continue

            # Detecta anatomia
            ctx = detect_anatomy(f, img=img_norm, hu_array=hu)
            print(f"  [{i}/{len(files)}] {f.name} -> {ctx.body_part.value} "
                  f"(conf={ctx.confidence:.2f}, src={ctx.source})")

            # Métricas universais
            universal = run_all_v2(img_norm)

            # Métricas anatomy-aware
            kwargs = {}
            if hu is not None:
                kwargs["hu_array"] = hu
            anatomy_metrics = run_anatomy_aware_metrics(ctx, img_norm, **kwargs)

            row = {
                **meta,
                "anatomy_body_part": ctx.body_part.value,
                "anatomy_laterality": ctx.laterality.value,
                "anatomy_view": ctx.view.value,
                "anatomy_confidence": ctx.confidence,
                "anatomy_source": ctx.source,
                **flatten({"universal": universal}),
                **flatten({"anatomy": anatomy_metrics}),
            }
            rows.append(row)

            if i % 50 == 0:
                el = time.time() - t0
                print(f"  {i}/{len(files)} ({el:.0f}s, {el/i:.2f}s/img)")

        print(f"  {mod.upper()} ok — {time.time()-t0:.0f}s total")

    df = pd.DataFrame(rows)
    csv = RESULTS / "anatomy_aware_metrics.csv"
    df.to_csv(csv, index=False)
    print(f"\nCSV: {csv} ({len(df)} linhas)")

    # Resumo por modalidade + anatomia
    if len(df) > 0 and "anatomy_body_part" in df.columns:
        print("\nResumo por modalidade/anatomia:")
        summary = df.groupby(["modality", "anatomy_body_part"]).size().reset_index(name="count")
        for _, row in summary.iterrows():
            print(f"  {row['modality']:3s} / {row['anatomy_body_part']:12s}: {row['count']:4d} imgs")


if __name__ == "__main__":
    main()
