"""Score unificado cross-modality.

Pra cada métrica que o scorecard marcou como 'keep':
  1. Z-normaliza dentro da modalidade (μ, σ por modalidade)
  2. Converte para percentil [0, 100]
  3. Inverte se a métrica é "menor=melhor" (NIQE, BRISQUE, ghosting,
     bias, motion_hf, ring, streak, hu_calibration, shadowing,
     anomaly_pct, mean_hu_drift)
  4. Pondera pelo `score` do scorecard (importância da métrica)
  5. Soma ponderada → score unificado 0-100

Saída:
  miqa/results/unified_scores.csv  (uma linha por imagem com score 0-100)
  miqa/results/_unified_section.html
"""
from __future__ import annotations
import base64, io
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).parent.parent
RESULTS = ROOT / "results"
SCORECARD_CSV = RESULTS / "metric_scorecard.csv"

# Métricas onde "menor = melhor" (subir significa pior qualidade)
LOWER_IS_BETTER = {
    "v2.niqe", "v2.brisque",
    "u.clipping_pct", "ct.air_noise", "ct.hu_calibration",
    "ct.ring", "ct.streak",
    "us.shadowing", "us.gain",
    "us_v2.tgc_cov",
    "rx_v2.nps_high_frac",
    "mri.ghosting", "mri.bias_field", "mri.motion_hf",
}


def col_in_quality_csv(metric_grid: str) -> str:
    """Converte nome 'rx.snr' (grid) → coluna do quality.csv 'rx.snr.value'."""
    if metric_grid == "v2.niqe": return "niqe"
    if metric_grid == "v2.brisque": return "brisque"
    if metric_grid.startswith("rx_v2."):
        return "v2." + metric_grid.split(".", 1)[1] + ".value"
    if metric_grid.startswith("us_v2."):
        return "v2." + metric_grid.split(".", 1)[1] + ".value"
    return metric_grid + ".value"


def load_full(mod: str) -> pd.DataFrame:
    """Junta v1 + v2 universal + v2 modalidade."""
    df = pd.read_csv(RESULTS / f"{mod}_quality.csv")
    v2u = RESULTS / "v2_metrics.csv"
    if v2u.exists():
        u = pd.read_csv(v2u)
        u = u[u.modality == mod][["file", "niqe", "brisque"]]
        df = df.merge(u, on="file", how="left")
    extra = RESULTS / f"{mod}_v2_metrics.csv"
    if extra.exists():
        ev = pd.read_csv(extra)
        if "file" in ev.columns:
            df = df.merge(ev, on="file", how="left")
    return df


def main():
    sc = pd.read_csv(SCORECARD_CSV)
    keep = sc[sc.decision == "keep"].copy()
    print(f"{len(keep)} métricas marcadas keep no scorecard")
    print(keep.groupby("modality").size().to_string())

    out_rows = []
    for mod in keep.modality.unique():
        df = load_full(mod)
        if df is None or df.empty: continue
        keep_mod = keep[keep.modality == mod]
        n = len(df)

        contributions = pd.DataFrame(index=df.index)
        weights = []
        for _, row in keep_mod.iterrows():
            metric = row.metric
            col = col_in_quality_csv(metric)
            if col not in df.columns:
                continue
            v = pd.to_numeric(df[col], errors="coerce")
            if v.notna().sum() < 5:
                continue
            # percentil 0-100 dentro da modalidade
            ranks = v.rank(method="average", pct=True) * 100
            if metric in LOWER_IS_BETTER:
                ranks = 100 - ranks
            # peso = score do scorecard
            w = float(row.score)
            contributions[metric] = ranks * w
            weights.append(w)

        if not weights:
            continue
        total_w = sum(weights)
        unified = contributions.sum(axis=1) / total_w
        df["_unified_score"] = unified
        for _, r in df.iterrows():
            out_rows.append({
                "modality": mod, "file": r["file"],
                "unified_score": float(r["_unified_score"]) if not pd.isna(r["_unified_score"]) else None,
                "n_keep_metrics": len(weights),
            })

    out = pd.DataFrame(out_rows)
    out.to_csv(RESULTS / "unified_scores.csv", index=False)
    print(f"\nCSV: unified_scores.csv ({len(out)} linhas)")
    print(out.groupby("modality").unified_score.describe().round(1).to_string())

    # plot — distribuição comparada
    fig, ax = plt.subplots(figsize=(9, 5), dpi=110)
    colors = {"rx": "#3a7", "us": "#37a", "ct": "#a73", "mri": "#a37"}
    for mod, g in out.groupby("modality"):
        s = g.unified_score.dropna()
        if len(s) == 0: continue
        ax.hist(s, bins=20, alpha=0.5, label=f"{mod.upper()} (n={len(s)}, med={s.median():.0f})",
                color=colors.get(mod, "gray"), edgecolor="white")
    ax.set_xlabel("Score unificado (0-100)")
    ax.set_ylabel("# imagens")
    ax.set_title("Distribuição do score unificado por modalidade")
    ax.legend()
    plt.tight_layout()
    buf = io.BytesIO(); fig.savefig(buf, format="png", bbox_inches="tight"); plt.close(fig)
    plot_b64 = base64.b64encode(buf.getvalue()).decode()

    # tabela top10 piores e melhores por modalidade
    tables_html = ""
    for mod in out.modality.unique():
        sub = out[out.modality == mod].dropna(subset=["unified_score"])
        if sub.empty: continue
        worst = sub.nsmallest(5, "unified_score")[["file", "unified_score"]]
        best = sub.nlargest(5, "unified_score")[["file", "unified_score"]]
        tables_html += f"""
<h3>{mod.upper()} — extremos</h3>
<div style="display: flex; gap: 20px;">
<div><b>5 piores</b>{worst.to_html(index=False, float_format=lambda x: f"{x:.1f}", classes="tbl")}</div>
<div><b>5 melhores</b>{best.to_html(index=False, float_format=lambda x: f"{x:.1f}", classes="tbl")}</div>
</div>"""

    html = f"""
<h2>Score unificado cross-modality (B)</h2>
<div class="legend">
<b>Como funciona:</b> só métricas marcadas <b>keep</b> no scorecard contribuem.
Cada uma é convertida para percentil [0,100] dentro de sua modalidade
(invertido se "menor=melhor"), depois ponderada pelo score do scorecard
e somada → 0 (pior) a 100 (melhor). <b>Comparável entre modalidades</b>
porque é puramente baseado em ranking interno.
</div>
<img src="data:image/png;base64,{plot_b64}" style="max-width:100%;"/>
{tables_html}
"""
    (RESULTS / "_unified_section.html").write_text(html)
    print(f"HTML: _unified_section.html")


if __name__ == "__main__":
    main()
