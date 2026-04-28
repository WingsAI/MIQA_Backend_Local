"""Relatório CONSOLIDADO MIQA — único HTML, recheado a cada experimento.

Lê CSVs existentes em miqa/results/ e produz:
  apresentacao_executivo/miqa-experiments.html  (servido pelo Vercel)

Idempotente: rodar de novo regenera tudo. Não toca em outros arquivos.

Uso: python -m miqa.pipelines.build_consolidated
"""
from __future__ import annotations
import base64, io
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).parent.parent
RESULTS = ROOT / "results"
OUT = ROOT.parent / "apresentacao_executivo" / "miqa-experiments.html"

V1_COLS = {
    "rx": [("rx.snr.value", "SNR"), ("rx.cnr.value", "CNR"),
           ("rx.exposure.value", "Exposure"), ("rx.edge_sharpness.value", "Sharpness"),
           ("u.entropy.value", "Entropy"), ("u.clipping_pct.value", "Clipping %")],
    "us": [("us.speckle_snr.value", "Speckle SNR"), ("us.shadowing.value", "Shadowing"),
           ("us.depth_of_penetration.value", "DoP"), ("us.gain.value", "Gain sat %"),
           ("u.entropy.value", "Entropy")],
    "ct": [("ct.air_noise.value", "σ ar (HU)"), ("ct.hu_calibration.value", "Δ HU calib"),
           ("ct.ring.value", "Ring residual"), ("ct.streak.value", "Streak"),
           ("u.entropy.value", "Entropy")],
    "mri": [("mri.nema_snr.value", "NEMA SNR"), ("mri.ghosting.value", "Ghosting"),
            ("mri.bias_field.value", "Bias field"), ("mri.motion_hf.value", "Motion HF"),
            ("u.entropy.value", "Entropy"), ("u.dynamic_range.value", "Dyn range")],
}

DATASET_INFO = {
    "rx": ("Kermany pediatric pneumonia (paultimothymooney)", "Kaggle • JPEG"),
    "us": ("BUSI breast ultrasound (sabahesaraki)", "Kaggle • PNG"),
    "ct": ("Stroke head DICOM (orvile/inme-veri-seti)", "Kaggle • DICOM HU"),
    "mri": ("Brain MRI dataset (simongraves/brain-mri-dataset)", "Kaggle • DICOM"),
}


def load_v1(modality: str) -> pd.DataFrame | None:
    f = RESULTS / f"{modality}_quality.csv"
    return pd.read_csv(f) if f.exists() else None


def load_v2() -> pd.DataFrame | None:
    f = RESULTS / "v2_metrics.csv"
    return pd.read_csv(f) if f.exists() else None


def load_rx_v2() -> pd.DataFrame | None:
    f = RESULTS / "rx_v2_metrics.csv"
    return pd.read_csv(f) if f.exists() else None


def load_us_v2() -> pd.DataFrame | None:
    f = RESULTS / "us_v2_metrics.csv"
    return pd.read_csv(f) if f.exists() else None


def fig_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def histograms_section(df: pd.DataFrame, modality: str) -> str:
    cols = V1_COLS[modality]
    n = len(cols)
    fig, axes = plt.subplots(2, 3, figsize=(11, 6), dpi=110)
    color = {"rx": "#3a7", "us": "#37a", "ct": "#a73", "mri": "#a37"}[modality]
    for ax, (c, label) in zip(axes.flat, cols):
        if c not in df.columns:
            ax.set_visible(False); continue
        v = pd.to_numeric(df[c], errors="coerce").dropna()
        ax.hist(v, bins=24, color=color, edgecolor="white")
        ax.axvline(v.median(), color="#c33", lw=1.5, label=f"med={v.median():.2f}")
        ax.set_title(label, fontsize=10)
        ax.tick_params(labelsize=8); ax.legend(fontsize=7)
    for ax in axes.flat[n:]:
        ax.set_visible(False)
    plt.tight_layout()
    return fig_b64(fig)


def stats_table(df: pd.DataFrame, modality: str) -> str:
    cols = [c for c, _ in V1_COLS[modality] if c in df.columns]
    sub = df[cols].apply(pd.to_numeric, errors="coerce")
    s = sub.describe().round(2).T[["count", "mean", "50%", "std", "min", "max"]]
    s.columns = ["n", "mean", "median", "std", "min", "max"]
    return s.to_html(classes="tbl", float_format=lambda x: f"{x:.2f}")


def corr_heatmap(df: pd.DataFrame, modality: str) -> str | None:
    cols_full = [(c, name) for c, name in V1_COLS[modality] if c in df.columns]
    extra_cols = [(c, c) for c in ("niqe", "brisque",
                                   "v2.lung_snr.value", "v2.nps_high_frac.value",
                                   "v2.speckle_anisotropy.value",
                                   "v2.lateral_resolution_px.value", "v2.tgc_cov.value")
                  if c in df.columns]
    pairs = cols_full + extra_cols
    if len(pairs) < 3:
        return None
    cols, labels = zip(*pairs)
    sub = df[list(cols)].apply(pd.to_numeric, errors="coerce")
    corr = sub.corr(method="spearman").round(2)
    fig, ax = plt.subplots(figsize=(7.5, 6.5), dpi=110)
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
    short = [l.replace("v2.", "").replace(".value", "")[:14] for l in labels]
    ax.set_xticks(range(len(short))); ax.set_yticks(range(len(short)))
    ax.set_xticklabels(short, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(short, fontsize=8)
    for i in range(len(short)):
        for j in range(len(short)):
            v = corr.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    fontsize=7, color="white" if abs(v) > 0.5 else "black")
    plt.colorbar(im, ax=ax, fraction=0.04)
    ax.set_title(f"Spearman {modality.upper()} (v1 + v2)")
    plt.tight_layout()
    return fig_b64(fig)


def section_modality(modality: str) -> str:
    df = load_v1(modality)
    if df is None:
        return f"<h2>{modality.upper()}</h2><p><i>sem dados ainda</i></p>"

    # join v2 universal (NIQE/BRISQUE)
    v2 = load_v2()
    if v2 is not None:
        v2_mod = v2[v2.modality == modality][["file", "niqe", "brisque"]]
        df = df.merge(v2_mod, on="file", how="left")
    if modality == "rx":
        rx_v2 = load_rx_v2()
        if rx_v2 is not None:
            df = df.merge(rx_v2, on="file", how="left")
    if modality == "us":
        us_v2 = load_us_v2()
        if us_v2 is not None:
            df = df.merge(us_v2, on="file", how="left")

    name, fmt = DATASET_INFO[modality]
    n = len(df)
    hist = histograms_section(df, modality)
    stats = stats_table(df, modality)
    heat = corr_heatmap(df, modality)
    heat_html = (f'<h3>Correlação Spearman (v1 + v2)</h3>'
                 f'<img src="data:image/png;base64,{heat}" style="max-width:100%;"/>'
                 if heat else "")
    extra_v2_summary = ""
    if "niqe" in df.columns:
        n_valid = df["niqe"].notna().sum()
        extra_v2_summary = f"""
<h3>Métricas v2 (NIQE/BRISQUE)</h3>
<p>NIQE mediana <b>{df['niqe'].median():.2f}</b> ({n_valid}/{n} válidas) ·
BRISQUE mediana <b>{df['brisque'].median():.2f}</b></p>"""
    if modality == "rx" and "v2.lung_snr.value" in df.columns:
        s = df["v2.lung_snr.value"].dropna()
        extra_v2_summary += f"""
<h3>Métricas RX v2 (NPS, lung_snr)</h3>
<p>lung_snr mediana <b>{s.median():.2f}</b> ({len(s)}/{n} válidas)<br>
nps_high_frac mediana <b>{df['v2.nps_high_frac.value'].median():.3f}</b></p>"""
    if modality == "us" and "v2.speckle_anisotropy.value" in df.columns:
        a = df["v2.speckle_anisotropy.value"].dropna()
        l = df["v2.lateral_resolution_px.value"].dropna()
        t = df["v2.tgc_cov.value"].dropna()
        extra_v2_summary += f"""
<h3>Métricas US v2 (speckle anisotropy, lateral resolution, TGC)</h3>
<p>speckle_anisotropy mediana <b>{a.median():.2f}</b> (1.0 = isotrópico ideal)<br>
lateral_resolution_px mediana <b>{l.median():.0f}</b> px (FWHM autocorrelação horizontal)<br>
tgc_cov mediana <b>{t.median():.3f}</b> (CoV de μ por linha; baixo = TGC bem ajustado)</p>"""

    return f"""
<h2>{modality.upper()}</h2>
<p class="meta-row"><b>Dataset:</b> {name} &nbsp;·&nbsp; <b>Formato:</b> {fmt} &nbsp;·&nbsp; <b>n:</b> {n}</p>
<h3>Distribuições (v1)</h3>
<img src="data:image/png;base64,{hist}" style="max-width:100%;"/>
<h3>Estatísticas</h3>
{stats}
{extra_v2_summary}
{heat_html}
"""


def overview() -> str:
    counts = {}
    for m in ("rx", "us", "ct", "mri"):
        df = load_v1(m)
        counts[m] = len(df) if df is not None else 0
    v2 = load_v2()
    rxv2 = load_rx_v2()
    usv2 = load_us_v2()
    return f"""
<table class="overview">
<tr><th>Modalidade</th><th>n imgs</th><th>Métricas v1</th><th>v2 (NIQE/BRISQUE)</th><th>v2 modalidade</th></tr>
<tr><td>RX</td><td>{counts['rx']}</td><td>SNR · CNR · exposure · sharpness</td>
    <td>{'✓' if v2 is not None else '—'}</td>
    <td>{'lung_snr · NPS' if rxv2 is not None else '—'}</td></tr>
<tr><td>US</td><td>{counts['us']}</td><td>speckle_snr · shadowing · DoP · gain</td>
    <td>{'✓' if v2 is not None else '—'}</td>
    <td>{'speckle_anisotropy · lateral_res · TGC' if usv2 is not None else '—'}</td></tr>
<tr><td>CT</td><td>{counts['ct']}</td><td>air_noise · HU calib · ring · streak</td>
    <td>{'✓' if v2 is not None else '—'}</td>
    <td>slice_consistency (volumes)</td></tr>
<tr><td>MRI</td><td>{counts['mri']}</td><td>NEMA SNR · ghosting · bias field · motion HF</td>
    <td>{'✓' if v2 is not None else '—'}</td><td>—</td></tr>
</table>"""


def degradation_section() -> str:
    f = RESULTS / "_degradation_section.html"
    return f.read_text() if f.exists() else ""


def scorecard_section() -> str:
    f = RESULTS / "_scorecard_section.html"
    return f.read_text() if f.exists() else ""


def unified_section() -> str:
    f = RESULTS / "_unified_section.html"
    return f.read_text() if f.exists() else ""


def main():
    sections = [section_modality(m) for m in ("rx", "us", "ct", "mri")]
    sections.append(degradation_section())
    sections.append(scorecard_section())
    sections.append(unified_section())
    html = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>MIQA — Experimentos (consolidado)</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 1100px; margin: 24px auto;
        padding: 0 24px; color: #222; background: #fafafa; }}
h1 {{ margin-bottom: 4px; }}
h2 {{ margin-top: 40px; padding-bottom: 6px; border-bottom: 2px solid #ccc; }}
h3 {{ margin-top: 20px; color: #555; font-weight: 600; }}
.meta {{ color: #888; font-size: 13px; }}
.meta-row {{ font-size: 14px; color: #444; margin-bottom: 8px; }}
.tbl {{ border-collapse: collapse; font-size: 13px; margin: 8px 0; }}
.tbl th, .tbl td {{ padding: 4px 10px; border: 1px solid #ddd; text-align: right; }}
.tbl th {{ background: #f0f0f0; text-align: left; }}
.tbl td:first-child, .tbl th:first-child {{ text-align: left; }}
.overview {{ border-collapse: collapse; font-size: 14px; margin: 16px 0 32px; width: 100%; }}
.overview th, .overview td {{ padding: 8px 12px; border: 1px solid #ddd; text-align: left; }}
.overview th {{ background: #f0f0f0; }}
.legend {{ background: #fff; border: 1px solid #ddd; padding: 14px 18px;
            border-radius: 4px; font-size: 14px; margin: 16px 0 28px; }}
img {{ display: block; margin: 8px 0; }}
code {{ background: #eee; padding: 2px 5px; border-radius: 3px; font-size: 0.9em; }}
</style></head><body>

<h1>MIQA — Experimentos consolidados</h1>
<div class="meta">Gerado em {datetime.now():%Y-%m-%d %H:%M} ·
relatório <b>único e vivo</b>, recheado a cada experimento.</div>

<div class="legend">
<b>Objetivo:</b> avaliar qualidade técnica de imagens médicas (RX, US, CT, MRI*) sem treinar
classificador. Cada métrica é validada em phantom sintético com degradação controlada
antes de ser aceita.<br>
<b>v1</b>: métricas físicas custom (SNR, CNR, HU calibration, etc.)<br>
<b>v2 universal</b>: NR-IQA clássicos (NIQE, BRISQUE) via <code>pyiqa</code><br>
<b>v2 modalidade</b>: métricas mais especializadas (NPS, máscara anatômica, etc.)<br>
* MRI ainda não implementada.
</div>

{overview()}

{''.join(sections)}

<h2>Próximos passos</h2>
<ul>
<li>F3 — US v2 (anisotropia speckle, lateral resolution)</li>
<li>F4 — CT v2 (slice consistency em volumes inteiros)</li>
<li>F5 — degradação controlada (curvas dose-resposta, score-card de utilidade)</li>
<li>F6 — adicionar MRI (fastMRI/IXI)</li>
</ul>

<div class="meta" style="margin-top:32px;">
Plano completo: <code>miqa/PLAN.md</code> ·
Código: <code>miqa/metrics/</code>, <code>miqa/pipelines/</code>
</div>
</body></html>
"""
    OUT.write_text(html)
    size_kb = len(html) / 1024
    print(f"OK — {OUT}  ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
