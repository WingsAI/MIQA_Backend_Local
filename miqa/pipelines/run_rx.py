"""Pipeline RX: lê DICOMs em miqa/data/rx_subset/, calcula universal+rx,
escreve CSV em miqa/results/rx_quality.csv e HTML resumo.

Uso: python -m miqa.pipelines.run_rx
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pydicom
import cv2

from miqa.metrics.universal import run_all as run_universal
from miqa.metrics.rx import run_all_rx

ROOT = Path(__file__).parent.parent
SUBSET = ROOT / "data" / "rx_subset"
RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


def load_rx(path: Path) -> tuple[np.ndarray, dict]:
    """Lê RX (DICOM ou PNG/JPG), retorna float32 [0,1] grayscale + metadados."""
    suf = path.suffix.lower()
    if suf == ".dcm":
        ds = pydicom.dcmread(path)
        arr = ds.pixel_array.astype(np.float32)
        photo = ds.get("PhotometricInterpretation", "MONOCHROME2")
        bits = int(ds.get("BitsStored", 16))
        a, b = float(arr.min()), float(arr.max())
        img = (arr - a) / max(b - a, 1e-9)
        if photo == "MONOCHROME1":
            img = 1.0 - img
        meta = {"file": path.name, "shape": str(arr.shape), "bits_stored": bits,
                "photometric": photo, "fmt": "dcm", "raw_min": a, "raw_max": b}
    elif suf in IMG_EXT:
        arr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if arr is None:
            raise ValueError(f"cv2.imread falhou em {path}")
        if arr.ndim == 3:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        arr = arr.astype(np.float32)
        a, b = float(arr.min()), float(arr.max())
        img = (arr - a) / max(b - a, 1e-9)
        bits = 16 if arr.dtype == np.uint16 else 8
        meta = {"file": path.name, "shape": str(arr.shape), "bits_stored": bits,
                "photometric": "PNG/JPG", "fmt": suf[1:], "raw_min": a, "raw_max": b}
    else:
        raise ValueError(f"extensão não suportada: {suf}")
    return img.astype(np.float32), meta


def flatten(d: dict, parent: str = "") -> dict:
    """Achata dict aninhado pra colunas de CSV."""
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
    for pat in ("*.dcm", "*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tif", "*.tiff"):
        files.extend(SUBSET.glob(pat))
    files = sorted(files)
    if not files:
        raise SystemExit(f"sem imagens em {SUBSET} — rode `python -m miqa.data.download_rx --src covid` antes")

    rows = []
    print(f"processando {len(files)} arquivos de {SUBSET}")
    for f in files:
        try:
            img, meta = load_rx(f)
        except Exception as e:
            print(f"  SKIP {f.name}: {e}")
            continue
        u = run_universal(img)
        r = run_all_rx(img)
        row = {**meta, **flatten({"u": u}), **flatten({"rx": r})}
        rows.append(row)
        print(f"  {f.name[:30]:30s}  SNR={r['snr']['value']:.1f}  CNR={r['cnr']['value']:.2f}"
              f"  exp={r['exposure']['flag']}  sharp={r['edge_sharpness']['value']:.0f}")

    df = pd.DataFrame(rows)
    csv_path = RESULTS / "rx_quality.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nCSV: {csv_path}  ({len(df)} linhas, {len(df.columns)} colunas)")

    # HTML report (sumário)
    summary_cols = [
        "file", "shape", "bits_stored", "photometric",
        "rx.snr.value", "rx.cnr.value", "rx.exposure.value", "rx.exposure.flag",
        "rx.edge_sharpness.value",
        "u.laplacian_var.value", "u.entropy.value",
        "u.clipping_pct.value", "u.dynamic_range.value",
    ]
    summary = df[[c for c in summary_cols if c in df.columns]].copy()
    summary.columns = [c.split(".")[-2] + "." + c.split(".")[-1] if "." in c else c
                       for c in summary.columns]
    html_path = RESULTS / "rx_quality.html"
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>MIQA RX Quality Report</title>
<style>
body {{ font-family: -apple-system,sans-serif; margin:24px; color:#222; }}
table {{ border-collapse:collapse; font-size:13px; }}
th, td {{ padding:6px 10px; border:1px solid #ddd; text-align:right; }}
th {{ background:#f5f5f5; text-align:left; }}
td:first-child, th:first-child {{ text-align:left; max-width:240px; overflow:hidden; text-overflow:ellipsis; }}
.flag-ok {{ color:#0a7; }} .flag-bad {{ color:#c33; font-weight:bold; }}
h1 {{ margin-bottom:4px; }} .meta {{ color:#888; font-size:13px; margin-bottom:16px; }}
</style></head><body>
<h1>MIQA RX Quality Report</h1>
<div class="meta">{datetime.now().isoformat(timespec='seconds')} — {len(df)} imagens — fonte: {SUBSET.name}</div>
{summary.to_html(index=False, float_format=lambda x: f"{x:.3f}")}
<h2>Estatísticas agregadas</h2>
{summary.describe().to_html(float_format=lambda x: f"{x:.3f}")}
</body></html>"""
    html_path.write_text(html)
    print(f"HTML: {html_path}")


if __name__ == "__main__":
    main()
