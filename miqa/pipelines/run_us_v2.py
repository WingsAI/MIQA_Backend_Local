"""Roda US v2 nas 100 imgs do us_subset → us_v2_metrics.csv."""
from __future__ import annotations
from pathlib import Path
import pandas as pd

from miqa.metrics.us_v2 import run_all_us_v2
from miqa.pipelines.run_us import load_us
from miqa.pipelines.run_rx import flatten

ROOT = Path(__file__).parent.parent
SUBSET = ROOT / "data" / "us_subset"
CSV_OUT = ROOT / "results" / "us_v2_metrics.csv"


def main():
    files = [f for f in sorted(SUBSET.glob("*"))
             if not f.name.startswith("._") and f.is_file()]
    rows = []
    print(f"US v2 em {len(files)} arquivos")
    for i, f in enumerate(files, 1):
        try:
            img, _ = load_us(f)
        except Exception as e:
            print(f"  SKIP {f.name}: {e}"); continue
        m = run_all_us_v2(img)
        rows.append({"file": f.name, **flatten({"v2": m})})
        if i % 25 == 0:
            print(f"  {i}/{len(files)}")
    df = pd.DataFrame(rows)
    df.to_csv(CSV_OUT, index=False)
    print(f"\nCSV: {CSV_OUT}  ({len(df)} linhas)")
    for c in ("v2.speckle_anisotropy.value", "v2.lateral_resolution_px.value", "v2.tgc_cov.value"):
        if c in df.columns:
            s = df[c].dropna()
            if len(s):
                print(f"  {c}  med={s.median():.3f}  p25={s.quantile(.25):.3f}  p75={s.quantile(.75):.3f}  válido={len(s)}/{len(df)}")


if __name__ == "__main__":
    main()
