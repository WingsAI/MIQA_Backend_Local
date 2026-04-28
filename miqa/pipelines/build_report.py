"""Gera HTML visual MIQA RX: thumbnails ordenados por qualidade + histogramas.

Lê miqa/results/rx_quality.csv e miqa/data/rx_subset/*, escreve:
  miqa/results/rx_report.html  (auto-contido com thumbs em base64)

Uso: python -m miqa.pipelines.build_report
"""
from __future__ import annotations
import base64
import io
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from miqa.pipelines.run_rx import load_rx

ROOT = Path(__file__).parent.parent
CSV = ROOT / "results" / "rx_quality.csv"
SUBSET = ROOT / "data" / "rx_subset"
OUT_HTML = ROOT / "results" / "rx_report.html"
THUMB_PX = 220


def img_to_b64(img: np.ndarray, label: str = "") -> str:
    """numpy float [0,1] -> PNG base64 com label sobreposto."""
    fig, ax = plt.subplots(figsize=(2.4, 2.4), dpi=100)
    ax.imshow(img, cmap="gray", vmin=0, vmax=1)
    if label:
        ax.text(0.02, 0.98, label, transform=ax.transAxes,
                fontsize=7, color="lime", va="top", family="monospace",
                bbox=dict(facecolor="black", alpha=0.6, pad=2, edgecolor="none"))
    ax.axis("off")
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def histograms_b64(df: pd.DataFrame) -> str:
    cols = [
        ("rx.snr.value", "SNR"),
        ("rx.cnr.value", "CNR"),
        ("rx.exposure.value", "Exposure"),
        ("rx.edge_sharpness.value", "Sharpness"),
        ("u.entropy.value", "Entropy"),
        ("u.clipping_pct.value", "Clipping %"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(11, 6), dpi=110)
    for ax, (c, label) in zip(axes.flat, cols):
        if c not in df.columns:
            ax.set_visible(False)
            continue
        v = df[c].dropna()
        ax.hist(v, bins=20, color="#3a7", edgecolor="white")
        ax.axvline(v.median(), color="#c33", lw=1.5, label=f"med={v.median():.2f}")
        ax.set_title(label, fontsize=10)
        ax.tick_params(labelsize=8)
        ax.legend(fontsize=7)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def quality_score(row) -> float:
    """Score agregado simples (0-100). Mais alto = melhor.
    Ponderação inicial — vamos ajustar com olho clínico depois."""
    snr = row.get("rx.snr.value", 0) or 0
    cnr = row.get("rx.cnr.value", 0) or 0
    sharp = row.get("rx.edge_sharpness.value", 0) or 0
    clip = row.get("u.clipping_pct.value", 100) or 100
    exp_flag = row.get("rx.exposure.flag", "")
    # normalizações empíricas (vão ser parametrizadas no autoresearch loop)
    s_snr = min(snr / 100, 1.0) * 30
    s_cnr = min(cnr / 80, 1.0) * 25
    s_sharp = min(sharp / 100, 1.0) * 20
    s_clip = max(0, 1 - clip / 20) * 15
    s_exp = 10 if exp_flag == "ok" else 0
    return round(s_snr + s_cnr + s_sharp + s_clip + s_exp, 1)


def main():
    df = pd.read_csv(CSV)
    df["score"] = df.apply(quality_score, axis=1)
    df = df.sort_values("score").reset_index(drop=True)

    print(f"montando relatório de {len(df)} imagens...")
    cards = []
    for _, row in df.iterrows():
        path = SUBSET / row["file"]
        if not path.exists():
            continue
        try:
            img, _ = load_rx(path)
        except Exception:
            continue
        # downsample p/ thumbnail (mantem proporção)
        h, w = img.shape
        scale = THUMB_PX / max(h, w)
        if scale < 1:
            from cv2 import resize, INTER_AREA
            img = resize(img, (int(w*scale), int(h*scale)), interpolation=INTER_AREA)
        label = (f"score {row['score']}\n"
                 f"SNR {row['rx.snr.value']:.0f}\n"
                 f"CNR {row['rx.cnr.value']:.0f}\n"
                 f"sharp {row['rx.edge_sharpness.value']:.0f}\n"
                 f"exp {row['rx.exposure.flag']}")
        b64 = img_to_b64(img, label)
        cards.append((row["score"], row["file"], b64))

    hist_b64 = histograms_b64(df)
    rows_html = "\n".join(
        f'<div class="card"><img src="data:image/png;base64,{b64}"/>'
        f'<div class="cap">{f}</div></div>'
        for _, f, b64 in cards
    )

    summary_cols = ["file", "score", "rx.snr.value", "rx.cnr.value",
                    "rx.exposure.flag", "rx.edge_sharpness.value",
                    "u.clipping_pct.value", "u.entropy.value"]
    summary_html = df[summary_cols].rename(columns={
        "rx.snr.value": "SNR", "rx.cnr.value": "CNR",
        "rx.exposure.flag": "exp_flag",
        "rx.edge_sharpness.value": "sharpness",
        "u.clipping_pct.value": "clip%",
        "u.entropy.value": "entropy",
    }).to_html(index=False, float_format=lambda x: f"{x:.2f}", classes="tbl")

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>MIQA RX — Visual Report</title>
<style>
body {{ font-family: -apple-system, sans-serif; margin: 24px; background: #fafafa; color: #222; }}
h1 {{ margin-bottom: 4px; }}
.meta {{ color: #888; font-size: 13px; margin-bottom: 20px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax({THUMB_PX+10}px, 1fr));
        gap: 8px; margin-top: 16px; }}
.card {{ background: white; border: 1px solid #ddd; border-radius: 4px; padding: 4px;
         box-shadow: 0 1px 2px rgba(0,0,0,0.05); }}
.card img {{ width: 100%; display: block; }}
.cap {{ font-size: 9px; color: #666; padding: 2px 4px; word-break: break-all; }}
.tbl {{ border-collapse: collapse; font-size: 12px; margin-top: 16px; }}
.tbl th, .tbl td {{ padding: 4px 8px; border: 1px solid #ddd; text-align: right; }}
.tbl th {{ background: #f0f0f0; }}
.tbl td:first-child, .tbl th:first-child {{ text-align: left; max-width: 280px;
            overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
h2 {{ margin-top: 32px; }}
.legend {{ background: #fff; border: 1px solid #ddd; padding: 12px; border-radius: 4px;
            font-size: 13px; margin-bottom: 16px; }}
</style></head><body>
<h1>MIQA RX — Visual Report</h1>
<div class="meta">{datetime.now():%Y-%m-%d %H:%M} — n={len(df)} imagens — score 0 (pior) → 100 (melhor)</div>

<div class="legend">
<b>Score</b> = SNR (×0.3) + CNR (×0.25) + sharpness (×0.20) + clipping_inv (×0.15) + exposure_ok (×0.10) → 0-100<br>
<b>Ordenação:</b> piores primeiro — primeiras imagens devem visualmente parecer ruins, últimas boas.
</div>

<h2>Histogramas</h2>
<img src="data:image/png;base64,{hist_b64}" style="max-width: 100%;"/>

<h2>Thumbnails (pior → melhor)</h2>
<div class="grid">{rows_html}</div>

<h2>Tabela completa</h2>
{summary_html}
</body></html>"""

    OUT_HTML.write_text(html)
    print(f"OK — {OUT_HTML}  ({len(html)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
