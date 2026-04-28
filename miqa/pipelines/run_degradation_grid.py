"""Grid dose-resposta: aplica todas as degradações em níveis k crescentes
em um subset de cada modalidade, calcula todas as métricas (v1+v2) em cada
estado degradado.

Saída: miqa/results/degradation_grid.csv
  colunas: modality, file, degradation, k, metric_name, value
  (formato long pra plot dose-resposta fácil)

Uso: python -m miqa.pipelines.run_degradation_grid [--n_per_mod 10]
"""
from __future__ import annotations
import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from miqa.synthetic.degradations_v2 import DEGRADATIONS
from miqa.metrics.universal import run_all as run_universal
from miqa.metrics.universal_v2 import niqe, brisque
from miqa.metrics.rx import run_all_rx
from miqa.metrics.us import run_all_us
from miqa.metrics.rx_v2 import run_all_rx_v2
from miqa.metrics.us_v2 import run_all_us_v2
from miqa.pipelines.run_rx import load_rx
from miqa.pipelines.run_us import load_us
from miqa.pipelines.run_ct import load_ct
from miqa.pipelines.run_mri import load_mri
from miqa.metrics.mri import run_all_mri

ROOT = Path(__file__).parent.parent
RESULTS = ROOT / "results"


def get_image(modality: str, path: Path) -> np.ndarray:
    """Retorna imagem [0,1] 2D float."""
    if modality == "rx":
        img, _ = load_rx(path)
    elif modality == "us":
        img, _ = load_us(path)
    elif modality == "ct":
        _, img, _ = load_ct(path)  # versão janelada
    elif modality == "mri":
        img, _ = load_mri(path)
    else:
        raise ValueError(modality)
    return img.astype(np.float32)


def compute_all_metrics(img: np.ndarray, modality: str) -> dict:
    """Roda todas as métricas aplicáveis e devolve dict flat metric_name→value."""
    out = {}
    u = run_universal(img)
    for k, v in u.items():
        out[f"u.{k}"] = v["value"]
    if modality == "rx":
        for k, v in run_all_rx(img).items():
            if k != "exposure":  # 'exposure' value é mediana, mas flag é string; pega só o valor
                out[f"rx.{k}"] = v["value"]
            else:
                out[f"rx.{k}"] = v["value"]
        for k, v in run_all_rx_v2(img).items():
            out[f"rx_v2.{k}"] = v["value"]
    elif modality == "us":
        for k, v in run_all_us(img).items():
            out[f"us.{k}"] = v["value"]
        for k, v in run_all_us_v2(img).items():
            out[f"us_v2.{k}"] = v["value"]
    elif modality == "mri":
        for k, v in run_all_mri(img).items():
            out[f"mri.{k}"] = v["value"]
    out["v2.niqe"] = niqe(img)[0]
    out["v2.brisque"] = brisque(img)[0]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n_per_mod", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    long_rows = []
    t0 = time.time()

    for modality in ("rx", "us", "ct", "mri"):
        subset = ROOT / "data" / f"{modality}_subset"
        files = [f for f in sorted(subset.glob("*"))
                 if f.is_file() and not f.name.startswith("._")]
        if not files: continue
        idx = rng.choice(len(files), size=min(args.n_per_mod, len(files)), replace=False)
        chosen = [files[i] for i in idx]
        print(f"\n=== {modality.upper()} — {len(chosen)} imgs ===")
        for fi, f in enumerate(chosen, 1):
            try:
                img0 = get_image(modality, f)
            except Exception as e:
                print(f"  SKIP {f.name}: {e}"); continue
            # baseline (k=0)
            m0 = compute_all_metrics(img0, modality)
            for name, v in m0.items():
                long_rows.append({"modality": modality, "file": f.name,
                                  "degradation": "none", "k": 0.0,
                                  "metric": name, "value": v})
            # cada degradação em cada nível k
            for deg_name, (fn, ks, _) in DEGRADATIONS.items():
                for k in ks:
                    try:
                        img_d = fn(img0, k)
                        m = compute_all_metrics(img_d, modality)
                    except Exception as e:
                        continue
                    for name, v in m.items():
                        long_rows.append({"modality": modality, "file": f.name,
                                          "degradation": deg_name, "k": float(k),
                                          "metric": name, "value": v})
            print(f"  {fi}/{len(chosen)}  {f.name[:30]:30s}  ({time.time()-t0:.0f}s elapsed)")

    df = pd.DataFrame(long_rows)
    csv = RESULTS / "degradation_grid.csv"
    df.to_csv(csv, index=False)
    print(f"\nCSV: {csv}  ({len(df)} linhas)")
    print(f"Tempo total: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
