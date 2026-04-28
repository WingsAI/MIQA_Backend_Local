"""Roda métricas RX v2 (NPS radial, lung_snr) nas 328 imgs do rx_subset
e mescla no rx_quality.csv como colunas extras.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

from miqa.metrics.rx_v2 import run_all_rx_v2
from miqa.pipelines.run_rx import load_rx, flatten

ROOT = Path(__file__).parent.parent
SUBSET = ROOT / "data" / "rx_subset"
CSV_V1 = ROOT / "results" / "rx_quality.csv"
CSV_OUT = ROOT / "results" / "rx_v2_metrics.csv"


def main():
    files = [f for f in sorted(SUBSET.glob("*"))
             if not f.name.startswith("._") and f.is_file()]
    rows = []
    print(f"RX v2 em {len(files)} arquivos")
    for i, f in enumerate(files, 1):
        try:
            img, _ = load_rx(f)
        except Exception as e:
            print(f"  SKIP {f.name}: {e}"); continue
        m = run_all_rx_v2(img)
        rows.append({"file": f.name, **flatten({"v2": m})})
        if i % 50 == 0:
            print(f"  {i}/{len(files)}")
    df_v2 = pd.DataFrame(rows)
    df_v2.to_csv(CSV_OUT, index=False)
    n_lung_ok = df_v2["v2.lung_snr.value"].notna().sum() if "v2.lung_snr.value" in df_v2.columns else 0
    n_nps_ok = df_v2["v2.nps_high_frac.value"].notna().sum() if "v2.nps_high_frac.value" in df_v2.columns else 0
    print(f"\nCSV: {CSV_OUT}  ({len(df_v2)} linhas)")
    print(f"  lung_snr válido em {n_lung_ok}/{len(df_v2)}")
    print(f"  nps_high_frac válido em {n_nps_ok}/{len(df_v2)}")
    if n_lung_ok:
        s = df_v2["v2.lung_snr.value"].dropna()
        print(f"  lung_snr  med={s.median():.2f} p25={s.quantile(.25):.2f} p75={s.quantile(.75):.2f}")
    if n_nps_ok:
        s = df_v2["v2.nps_high_frac.value"].dropna()
        print(f"  nps_high_frac med={s.median():.3f} p25={s.quantile(.25):.3f} p75={s.quantile(.75):.3f}")


if __name__ == "__main__":
    main()
