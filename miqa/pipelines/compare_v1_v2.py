"""Compara métricas v1 (custom) vs v2 (NIQE/BRISQUE) nos 3 subsets.

Saída: miqa/results/compare_v1_v2.html — uma seção por modalidade com:
  - matriz de correlação Spearman entre métricas v1 e v2
  - scatter v1×v2 das mais relevantes
  - top-10 imagens onde v1 e v2 mais discordam (rank-diff)

Uso: python -m miqa.pipelines.compare_v1_v2
"""
from __future__ import annotations
import base64, io
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).parent.parent
RESULTS = ROOT / "results"
OUT_HTML = RESULTS / "compare_v1_v2.html"

# v1 cols por modalidade (excluindo flags string)
V1_COLS = {
    "rx": ["rx.snr.value", "rx.cnr.value", "rx.exposure.value",
           "rx.edge_sharpness.value", "u.entropy.value", "u.clipping_pct.value"],
    "us": ["us.speckle_snr.value", "us.shadowing.value",
           "us.depth_of_penetration.value", "u.entropy.value", "u.dynamic_range.value"],
    "ct": ["ct.air_noise.value", "ct.hu_calibration.value",
           "ct.ring.value", "ct.streak.value", "u.entropy.value"],
}
V2_COLS = ["niqe", "brisque"]


def load_combined(modality: str) -> pd.DataFrame:
    v1 = pd.read_csv(RESULTS / f"{modality}_quality.csv")
    v2 = pd.read_csv(RESULTS / "v2_metrics.csv")
    v2_mod = v2[v2.modality == modality].set_index("file")
    df = v1.set_index("file").join(v2_mod[V2_COLS], how="left").reset_index()
    return df


def fig_corr(df: pd.DataFrame, modality: str) -> str:
    cols = [c for c in V1_COLS[modality] + V2_COLS if c in df.columns]
    sub = df[cols].apply(pd.to_numeric, errors="coerce")
    corr = sub.corr(method="spearman").round(2)
    fig, ax = plt.subplots(figsize=(7.5, 6.5), dpi=110)
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(cols))); ax.set_yticks(range(len(cols)))
    short = [c.replace(".value", "").replace("rx.", "").replace("us.", "")
              .replace("ct.", "").replace("u.", "") for c in cols]
    ax.set_xticklabels(short, rotation=45, ha="right", fontsize=9)
    ax.set_yticklabels(short, fontsize=9)
    for i in range(len(cols)):
        for j in range(len(cols)):
            v = corr.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    fontsize=8, color="white" if abs(v) > 0.5 else "black")
    plt.colorbar(im, ax=ax, fraction=0.04)
    ax.set_title(f"Spearman {modality.upper()} (v1 + v2)")
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight"); plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def fig_scatters(df: pd.DataFrame, modality: str) -> str:
    """Scatter de cada métrica v1 mais informativa contra NIQE e BRISQUE."""
    pairs = []
    for v1c in V1_COLS[modality][:4]:
        if v1c in df.columns:
            for v2c in V2_COLS:
                if v2c in df.columns:
                    pairs.append((v1c, v2c))
    n = len(pairs)
    if n == 0:
        return ""
    cols = 4
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.6, rows * 2.4), dpi=110)
    axes = np.atleast_2d(axes).flatten()
    for ax, (v1c, v2c) in zip(axes, pairs):
        x = pd.to_numeric(df[v1c], errors="coerce")
        y = pd.to_numeric(df[v2c], errors="coerce")
        ax.scatter(x, y, s=8, alpha=0.5)
        ax.set_xlabel(v1c.replace(".value", "").split(".")[-1], fontsize=8)
        ax.set_ylabel(v2c, fontsize=8)
        ax.tick_params(labelsize=7)
        valid = x.notna() & y.notna()
        if valid.sum() > 3:
            r = x[valid].corr(y[valid], method="spearman")
            ax.text(0.05, 0.95, f"ρ={r:.2f}", transform=ax.transAxes,
                    fontsize=8, va="top",
                    bbox=dict(facecolor="white", alpha=0.7, pad=2, edgecolor="none"))
    for ax in axes[len(pairs):]:
        ax.set_visible(False)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight"); plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def discordant(df: pd.DataFrame, modality: str, top_k: int = 10) -> pd.DataFrame:
    """Imagens onde rank por v1 (score já calculado em rx/us/ct CSV) e por NIQE divergem."""
    if "score" not in df.columns:
        # se não tem score, usa SNR/speckle/calib como proxy v1
        proxy_map = {
            "rx": "rx.snr.value", "us": "us.speckle_snr.value", "ct": "ct.air_noise.value"
        }
        df = df.copy()
        df["score"] = pd.to_numeric(df[proxy_map[modality]], errors="coerce")
    rank_v1 = df["score"].rank(method="average")
    rank_v2 = df["niqe"].rank(method="average", ascending=False)  # NIQE menor=melhor → invert
    df = df.assign(rank_v1=rank_v1, rank_v2=rank_v2,
                   rank_diff=(rank_v1 - rank_v2).abs())
    cols = ["file", "score", "niqe", "brisque", "rank_v1", "rank_v2", "rank_diff"]
    return df.nlargest(top_k, "rank_diff")[cols].round(2)


def main():
    sections = []
    for mod in ("rx", "us", "ct"):
        try:
            df = load_combined(mod)
        except FileNotFoundError as e:
            print(f"skip {mod}: {e}"); continue
        n = len(df)
        n_valid_v2 = df[V2_COLS].notna().all(axis=1).sum()
        corr_b64 = fig_corr(df, mod)
        scat_b64 = fig_scatters(df, mod)
        disc_html = discordant(df, mod).to_html(index=False, classes="tbl",
                                                 float_format=lambda x: f"{x:.2f}")
        sections.append(f"""
<h2>{mod.upper()} — n={n} (v2 válido: {n_valid_v2})</h2>
<h3>Correlação Spearman</h3>
<img src="data:image/png;base64,{corr_b64}" style="max-width: 100%;"/>
<h3>Scatter v1 × v2</h3>
<img src="data:image/png;base64,{scat_b64}" style="max-width: 100%;"/>
<h3>Top 10 mais discordantes (rank v1 vs NIQE-invert)</h3>
{disc_html}
""")

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>MIQA — v1 vs v2 Comparison</title>
<style>
body {{ font-family: -apple-system, sans-serif; margin: 24px; color: #222; background: #fafafa; }}
h2 {{ margin-top: 36px; border-bottom: 2px solid #ccc; padding-bottom: 4px; }}
.tbl {{ border-collapse: collapse; font-size: 12px; }}
.tbl th, .tbl td {{ padding: 4px 8px; border: 1px solid #ddd; text-align: right; }}
.tbl th {{ background: #f0f0f0; }}
.tbl td:first-child, .tbl th:first-child {{ text-align: left;
            max-width: 280px; overflow: hidden; text-overflow: ellipsis;
            white-space: nowrap; }}
.legend {{ background: #fff; border: 1px solid #ddd; padding: 12px; border-radius: 4px;
            font-size: 13px; }}
</style></head><body>
<h1>MIQA — v1 (custom) vs v2 (NIQE/BRISQUE)</h1>
<div class="legend">
<b>v1</b>: nossas métricas físicas (SNR, CNR, exposure, sharpness, calib HU, etc.)<br>
<b>v2</b>: NR-IQA clássico baseado em estatísticas naturais.<br>
ρ alto = v1 e v2 concordam. ρ baixo = capturam coisas diferentes (potencialmente complementar).
</div>
{''.join(sections)}
<div class="meta" style="color:#888;font-size:13px;margin-top:32px;">
Gerado em {datetime.now():%Y-%m-%d %H:%M}
</div>
</body></html>"""
    OUT_HTML.write_text(html)
    print(f"OK — {OUT_HTML}")


if __name__ == "__main__":
    main()
