"""HTML visual MIQA CT — thumbnails ordenados + histogramas."""
from __future__ import annotations
import base64, io
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from miqa.pipelines.run_ct import load_ct

ROOT = Path(__file__).parent.parent
CSV = ROOT / "results" / "ct_quality.csv"
SUBSET = ROOT / "data" / "ct_subset"
OUT_HTML = ROOT / "results" / "ct_report.html"
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


def histograms_b64(df):
    cols = [
        ("ct.air_noise.value", "σ ar (HU)"),
        ("ct.hu_calibration.value", "Desvio HU (ar)"),
        ("ct.ring.value", "Ring residual (HU)"),
        ("ct.streak.value", "Streak"),
        ("u.entropy.value", "Entropy"),
        ("u.dynamic_range.value", "Dynamic range"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(11, 6), dpi=110)
    for ax, (c, label) in zip(axes.flat, cols):
        if c not in df.columns:
            ax.set_visible(False); continue
        v = df[c].dropna()
        ax.hist(v, bins=30, color="#a73", edgecolor="white")
        ax.axvline(v.median(), color="#c33", lw=1.5, label=f"med={v.median():.2f}")
        ax.set_title(label, fontsize=10); ax.tick_params(labelsize=8)
        ax.legend(fontsize=7)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def quality_score(row) -> float:
    """Score CT 0-100 — calibração ok, ruído ar baixo, ring/streak baixos, entropia ok."""
    calib_ok = row.get("ct.hu_calibration.flag", "") == "ok"
    air_n = row.get("ct.air_noise.value", 100) or 100
    ring = row.get("ct.ring.value", 100) or 100
    streak = row.get("ct.streak.value", 1000) or 1000
    entropy = row.get("u.entropy.value", 0) or 0
    s_calib = 30 if calib_ok else 0
    s_air = max(0, 1 - air_n / 30) * 25
    s_ring = max(0, 1 - ring / 30) * 15
    s_streak = max(0, 1 - streak / 500) * 15
    s_entropy = min(entropy / 5, 1.0) * 15
    return round(s_calib + s_air + s_ring + s_streak + s_entropy, 1)


def main():
    df = pd.read_csv(CSV)
    df["score"] = df.apply(quality_score, axis=1)
    df = df.sort_values("score").reset_index(drop=True)
    print(f"montando relatório CT n={len(df)} (todas processadas)...")

    # Pra acelerar, gera thumbs apenas das 60 primeiras + 60 últimas + 30 medianas
    n = len(df)
    if n > 150:
        idx = list(range(60)) + list(range(n//2 - 15, n//2 + 15)) + list(range(n - 60, n))
    else:
        idx = list(range(n))
    cards = []
    for i in idx:
        row = df.iloc[i]
        path = SUBSET / row["file"]
        if not path.exists(): continue
        try:
            _, norm, _ = load_ct(path)
        except Exception: continue
        h, w = norm.shape
        scale = THUMB_PX / max(h, w)
        if scale < 1:
            from cv2 import resize, INTER_AREA
            norm = resize(norm, (int(w*scale), int(h*scale)), interpolation=INTER_AREA)
        label = (f"score {row['score']}\n"
                 f"σ_ar {row['ct.air_noise.value']:.1f} HU\n"
                 f"calib {row['ct.hu_calibration.flag']}\n"
                 f"ring {row['ct.ring.value']:.1f}\n"
                 f"streak {row['ct.streak.value']:.0f}")
        cards.append((row["score"], row["file"], img_to_b64(norm, label)))

    hist_b64 = histograms_b64(df)
    rows_html = "\n".join(
        f'<div class="card"><img src="data:image/png;base64,{b64}"/>'
        f'<div class="cap">{f}</div></div>'
        for _, f, b64 in cards
    )

    summary_cols = ["file", "score", "ct.air_noise.value",
                    "ct.hu_calibration.value", "ct.hu_calibration.flag",
                    "ct.ring.value", "ct.streak.value", "u.entropy.value"]
    summary_html = df[summary_cols].rename(columns={
        "ct.air_noise.value": "σ_ar_HU",
        "ct.hu_calibration.value": "calib_dev",
        "ct.hu_calibration.flag": "calib",
        "ct.ring.value": "ring",
        "ct.streak.value": "streak",
        "u.entropy.value": "entropy",
    }).to_html(index=False, float_format=lambda x: f"{x:.2f}", classes="tbl")

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>MIQA CT — Visual Report</title>
<style>
body {{ font-family: -apple-system, sans-serif; margin: 24px; background: #fafafa; color: #222; }}
.meta {{ color: #888; font-size: 13px; margin-bottom: 20px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax({THUMB_PX+10}px, 1fr));
        gap: 8px; margin-top: 16px; }}
.card {{ background: white; border: 1px solid #ddd; border-radius: 4px; padding: 4px; }}
.card img {{ width: 100%; display: block; }}
.cap {{ font-size: 9px; color: #666; padding: 2px 4px; word-break: break-all; }}
.tbl {{ border-collapse: collapse; font-size: 11px; margin-top: 16px; }}
.tbl th, .tbl td {{ padding: 3px 6px; border: 1px solid #ddd; text-align: right; }}
.tbl th {{ background: #f0f0f0; }}
.tbl td:first-child, .tbl th:first-child {{ text-align: left; max-width: 200px;
            overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.legend {{ background: #fff; border: 1px solid #ddd; padding: 12px; border-radius: 4px;
            font-size: 13px; margin-bottom: 16px; }}
.note {{ background: #fff8e1; border-left: 3px solid #c90; padding: 10px 14px;
         font-size: 13px; margin: 14px 0; }}
</style></head><body>
<h1>MIQA CT — Visual Report</h1>
<div class="meta">{datetime.now():%Y-%m-%d %H:%M} — n={n} imagens — pior → melhor (mostrando 60 piores + 30 medianas + 60 melhores)</div>

<div class="legend">
<b>Score CT</b> = calib_ok (×0.30) + air_noise_inv (×0.25) + ring_inv (×0.15)
+ streak_inv (×0.15) + entropy (×0.15) → 0-100
</div>

<div class="note">
<b>Nota:</b> dataset stroke turco tem DICOMs com cabeçalhos heterogêneos —
~66% têm RescaleIntercept inconsistente, e cantos contêm crânio (não ar)
em CT cranial. Score reflete isso. Para CT abdominal/pulmonar a métrica
hu_calibration teria menor falso-positivo.
</div>

<h2>Histogramas</h2>
<img src="data:image/png;base64,{hist_b64}" style="max-width: 100%;"/>

<h2>Thumbnails</h2>
<div class="grid">{rows_html}</div>

<h2>Tabela completa</h2>
{summary_html}
</body></html>"""
    OUT_HTML.write_text(html)
    print(f"OK — {OUT_HTML}")


if __name__ == "__main__":
    main()
