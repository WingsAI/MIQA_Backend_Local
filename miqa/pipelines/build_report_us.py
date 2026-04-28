"""HTML visual MIQA US — thumbnails ordenados por qualidade + histogramas."""
from __future__ import annotations
import base64, io
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from miqa.pipelines.run_us import load_us

ROOT = Path(__file__).parent.parent
CSV = ROOT / "results" / "us_quality.csv"
SUBSET = ROOT / "data" / "us_subset"
OUT_HTML = ROOT / "results" / "us_report.html"
THUMB_PX = 220


def img_to_b64(img: np.ndarray, label: str = "") -> str:
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
        ("us.speckle_snr.value", "Speckle SNR"),
        ("us.shadowing.value", "Shadowing"),
        ("us.depth_of_penetration.value", "DoP"),
        ("us.gain.value", "Gain saturation %"),
        ("u.entropy.value", "Entropy"),
        ("u.dynamic_range.value", "Dynamic Range"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(11, 6), dpi=110)
    for ax, (c, label) in zip(axes.flat, cols):
        if c not in df.columns:
            ax.set_visible(False); continue
        v = df[c].dropna()
        ax.hist(v, bins=20, color="#37a", edgecolor="white")
        ax.axvline(v.median(), color="#c33", lw=1.5, label=f"med={v.median():.2f}")
        ax.set_title(label, fontsize=10); ax.tick_params(labelsize=8)
        ax.legend(fontsize=7)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def quality_score(row) -> float:
    """Score 0-100 para US — speckle SNR alto, shadowing baixo, DoP alto, gain ok."""
    snr = row.get("us.speckle_snr.value", 0) or 0
    shadow = row.get("us.shadowing.value", 1) or 1
    dop = row.get("us.depth_of_penetration.value", 0) or 0
    gain = row.get("us.gain.flag", "")
    entropy = row.get("u.entropy.value", 0) or 0
    s_snr = min(snr / 4, 1.0) * 30        # SNR útil até ~4
    s_shadow = max(0, 1 - shadow * 4) * 20 # 0% sombra → 20, 25%+ → 0
    s_dop = min(dop, 1.0) * 25
    s_gain = 15 if gain == "ok" else 0
    s_entropy = min(entropy / 8, 1.0) * 10
    return round(s_snr + s_shadow + s_dop + s_gain + s_entropy, 1)


def main():
    df = pd.read_csv(CSV)
    df["score"] = df.apply(quality_score, axis=1)
    df = df.sort_values("score").reset_index(drop=True)
    print(f"montando relatório US n={len(df)}...")

    cards = []
    for _, row in df.iterrows():
        path = SUBSET / row["file"]
        if not path.exists():
            continue
        try:
            img, _ = load_us(path)
        except Exception:
            continue
        h, w = img.shape
        scale = THUMB_PX / max(h, w)
        if scale < 1:
            from cv2 import resize, INTER_AREA
            img = resize(img, (int(w*scale), int(h*scale)), interpolation=INTER_AREA)
        label = (f"score {row['score']}\n"
                 f"speckle {row['us.speckle_snr.value']:.2f}\n"
                 f"shadow {row['us.shadowing.value']:.2f}\n"
                 f"DoP {row['us.depth_of_penetration.value']:.2f}\n"
                 f"gain {row['us.gain.flag']}")
        cards.append((row["score"], row["file"], img_to_b64(img, label)))

    hist_b64 = histograms_b64(df)
    rows_html = "\n".join(
        f'<div class="card"><img src="data:image/png;base64,{b64}"/>'
        f'<div class="cap">{f}</div></div>'
        for _, f, b64 in cards
    )
    summary_cols = ["file", "score", "us.speckle_snr.value", "us.shadowing.value",
                    "us.depth_of_penetration.value", "us.gain.flag",
                    "u.entropy.value", "u.dynamic_range.value"]
    summary_html = df[summary_cols].rename(columns={
        "us.speckle_snr.value": "speckle_snr",
        "us.shadowing.value": "shadow",
        "us.depth_of_penetration.value": "DoP",
        "us.gain.flag": "gain",
        "u.entropy.value": "entropy",
        "u.dynamic_range.value": "dyn_range",
    }).to_html(index=False, float_format=lambda x: f"{x:.2f}", classes="tbl")

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>MIQA US — Visual Report</title>
<style>
body {{ font-family: -apple-system, sans-serif; margin: 24px; background: #fafafa; color: #222; }}
.meta {{ color: #888; font-size: 13px; margin-bottom: 20px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax({THUMB_PX+10}px, 1fr));
        gap: 8px; margin-top: 16px; }}
.card {{ background: white; border: 1px solid #ddd; border-radius: 4px; padding: 4px; }}
.card img {{ width: 100%; display: block; }}
.cap {{ font-size: 9px; color: #666; padding: 2px 4px; word-break: break-all; }}
.tbl {{ border-collapse: collapse; font-size: 12px; margin-top: 16px; }}
.tbl th, .tbl td {{ padding: 4px 8px; border: 1px solid #ddd; text-align: right; }}
.tbl th {{ background: #f0f0f0; }}
.tbl td:first-child, .tbl th:first-child {{ text-align: left; max-width: 280px;
            overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.legend {{ background: #fff; border: 1px solid #ddd; padding: 12px; border-radius: 4px;
            font-size: 13px; margin-bottom: 16px; }}
</style></head><body>
<h1>MIQA US — Visual Report</h1>
<div class="meta">{datetime.now():%Y-%m-%d %H:%M} — n={len(df)} imagens — pior → melhor</div>

<div class="legend">
<b>Score US</b> = speckle_snr (×0.30) + shadow_inv (×0.20) + DoP (×0.25)
+ gain_ok (×0.15) + entropy (×0.10) → 0-100
</div>

<h2>Histogramas</h2>
<img src="data:image/png;base64,{hist_b64}" style="max-width: 100%;"/>

<h2>Thumbnails</h2>
<div class="grid">{rows_html}</div>

<h2>Tabela</h2>
{summary_html}
</body></html>"""
    OUT_HTML.write_text(html)
    print(f"OK — {OUT_HTML}")


if __name__ == "__main__":
    main()
