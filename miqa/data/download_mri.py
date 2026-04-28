"""Baixa subset MRI DICOM via Kaggle CLI.

Datasets:
  brain  — simongraves/brain-mri-dataset       (125 MB, DICOM brain T1/T2)
  pet    — grantmcnatt/mri-and-pet-dice...     (13 MB, DICOM brain MRI+PET)

Uso: python -m miqa.data.download_mri --src brain --n 200
"""
from __future__ import annotations
import argparse
import random
import shutil
import subprocess
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
KAGGLE = "/Users/iaparamedicos/envs/dev/bin/kaggle"

DATASETS = {
    "brain": "simongraves/brain-mri-dataset",
    "pet":   "grantmcnatt/mri-and-pet-dice-similarity-dataset",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", choices=list(DATASETS), default="brain")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    raw = DATA_DIR / f"mri_raw_{args.src}"
    sub = DATA_DIR / "mri_subset"
    raw.mkdir(parents=True, exist_ok=True)
    sub.mkdir(parents=True, exist_ok=True)

    print(f"[1/3] kaggle datasets download {DATASETS[args.src]} -> {raw}")
    subprocess.run([KAGGLE, "datasets", "download", DATASETS[args.src],
                    "-p", str(raw), "--unzip"], check=True)

    files = sorted(raw.rglob("*.dcm"))
    print(f"[2/3] {len(files)} DICOMs encontrados")
    if not files:
        sys.exit("ERRO: sem .dcm")

    for f in sub.iterdir(): f.unlink()
    random.seed(args.seed)
    pick = random.sample(files, min(args.n, len(files)))
    print(f"[3/3] copiando {len(pick)} -> {sub}")
    for p in pick:
        safe = p.name.encode("ascii", "ignore").decode() or f"mri_{hash(str(p)) & 0xffff}.dcm"
        shutil.copy(p, sub / safe)
    total_mb = sum(f.stat().st_size for f in sub.iterdir()) / 1e6
    print(f"OK — {len(pick)} arquivos, {total_mb:.1f} MB")


if __name__ == "__main__":
    main()
