"""Roda métricas v2 (NIQE, BRISQUE) nos 3 subsets já existentes e produz
um CSV unificado v2_metrics.csv com:
  modality, file, niqe, brisque

Carrega cada imagem usando o loader já apropriado da modalidade.

Uso: python -m miqa.pipelines.run_v2 [--modality rx|us|ct|all]
"""
from __future__ import annotations
import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from miqa.metrics.universal_v2 import niqe, brisque
from miqa.pipelines.run_rx import load_rx
from miqa.pipelines.run_us import load_us
from miqa.pipelines.run_ct import load_ct
from miqa.pipelines.run_mri import load_mri

ROOT = Path(__file__).parent.parent

LOADERS = {
    "rx":  (load_rx,  ROOT / "data" / "rx_subset",  "*"),
    "us":  (load_us,  ROOT / "data" / "us_subset",  "*"),
    "ct":  (load_ct,  ROOT / "data" / "ct_subset",  "*.dcm"),
    "mri": (load_mri, ROOT / "data" / "mri_subset", "*.dcm"),
}


def is_real(p: Path) -> bool:
    return not p.name.startswith("._")


def get_norm(modality: str, path: Path) -> np.ndarray:
    """Cada loader retorna shape diferente — extrair img normalizada [0,1] 2D."""
    loader, _, _ = LOADERS[modality]
    out = loader(path)
    if modality == "ct":
        # load_ct → (hu, norm, meta)
        return out[1]
    return out[0]  # (img, meta)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modality", choices=["rx", "us", "ct", "mri", "all"], default="all")
    args = ap.parse_args()

    mods = ["rx", "us", "ct", "mri"] if args.modality == "all" else [args.modality]
    rows = []
    for mod in mods:
        loader, subset_dir, pattern = LOADERS[mod]
        files = [f for f in sorted(subset_dir.glob(pattern)) if is_real(f)]
        print(f"\n=== {mod.upper()} (n={len(files)}) ===")
        t0 = time.time()
        for i, f in enumerate(files, 1):
            try:
                img = get_norm(mod, f)
            except Exception as e:
                print(f"  SKIP {f.name}: {e}"); continue
            v_niqe, _ = niqe(img)
            v_brisque, _ = brisque(img)
            rows.append({
                "modality": mod, "file": f.name,
                "niqe": v_niqe, "brisque": v_brisque,
            })
            if i % 50 == 0:
                el = time.time() - t0
                print(f"  {i}/{len(files)}  ({el:.0f}s, {el/i:.2f}s/img)")
        print(f"  {mod.upper()} ok — {time.time()-t0:.0f}s total")

    df = pd.DataFrame(rows)
    csv = ROOT / "results" / "v2_metrics.csv"
    df.to_csv(csv, index=False)
    print(f"\nCSV: {csv}  ({len(df)} linhas)")
    for mod in mods:
        sub = df[df.modality == mod]
        if len(sub):
            print(f"  {mod.upper():3s}: NIQE med={sub.niqe.median():.2f}  "
                  f"BRISQUE med={sub.brisque.median():.2f}")


if __name__ == "__main__":
    main()
