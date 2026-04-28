"""Constrói a seção de degradação (dose-resposta + scorecard) que será
embutida no consolidado.

Saída: miqa/results/_degradation_section.html  (snippet, lido por build_consolidated)
"""
from __future__ import annotations
import base64, io
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from miqa.synthetic.degradations_v2 import DEGRADATIONS

ROOT = Path(__file__).parent.parent
GRID = ROOT / "results" / "degradation_grid.csv"
OUT = ROOT / "results" / "_degradation_section.html"


def fig_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight"); plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


# Métricas a plotar por modalidade (ID do CSV → label no plot)
PLOT_METRICS = {
    "rx": [("rx.snr", "SNR"), ("rx.cnr", "CNR"),
           ("rx.edge_sharpness", "edge_sharp"),
           ("rx_v2.lung_snr", "lung_SNR"),
           ("rx_v2.nps_high_frac", "NPS hi"),
           ("u.laplacian_var", "lap_var"),
           ("u.laplacian_snr", "lap_snr"),
           ("u.entropy", "entropy"),
           ("v2.niqe", "NIQE"),
           ("v2.brisque", "BRISQUE")],
    "us": [("us.speckle_snr", "speckle_SNR"),
           ("us.shadowing", "shadow"),
           ("us.depth_of_penetration", "DoP"),
           ("us_v2.speckle_anisotropy", "anisotropy"),
           ("us_v2.tgc_cov", "tgc_cov"),
           ("u.laplacian_var", "lap_var"),
           ("u.laplacian_snr", "lap_snr"),
           ("u.entropy", "entropy"),
           ("v2.niqe", "NIQE"),
           ("v2.brisque", "BRISQUE")],
    "ct": [("ct.air_noise", "σ_ar"),
           ("ct.hu_calibration", "Δ HU"),
           ("ct.ring", "ring"),
           ("ct.streak", "streak"),
           ("u.laplacian_var", "lap_var"),
           ("u.laplacian_snr", "lap_snr"),
           ("u.entropy", "entropy"),
           ("v2.niqe", "NIQE"),
           ("v2.brisque", "BRISQUE")],
    "mri": [("mri.nema_snr", "NEMA_SNR"),
            ("mri.ghosting", "ghosting"),
            ("mri.bias_field", "bias"),
            ("mri.motion_hf", "motion_HF"),
            ("u.laplacian_var", "lap_var"),
            ("u.laplacian_snr", "lap_snr"),
            ("u.entropy", "entropy"),
            ("v2.niqe", "NIQE"),
            ("v2.brisque", "BRISQUE")],
}


def dose_response_grid(df: pd.DataFrame, modality: str) -> str:
    """Para cada degradação, plota mediana(metric)/mediana(metric_baseline) vs k.
    Painel: linhas = degradações, colunas = métricas."""
    sub = df[df.modality == modality]
    if sub.empty:
        return ""
    metrics_to_plot = [m for m, _ in PLOT_METRICS[modality]
                        if m in sub.metric.unique()]
    labels_map = dict(PLOT_METRICS[modality])
    degs = list(DEGRADATIONS.keys())
    n_rows = len(degs)
    n_cols = len(metrics_to_plot)
    if n_cols == 0:
        return ""
    fig, axes = plt.subplots(n_rows, n_cols,
                              figsize=(n_cols * 1.7, n_rows * 1.5),
                              dpi=110, sharex='row')
    axes = np.atleast_2d(axes)
    for i, deg in enumerate(degs):
        for j, metric in enumerate(metrics_to_plot):
            ax = axes[i, j]
            base = sub[(sub.degradation == "none") & (sub.metric == metric)]
            base_med = base.value.median()
            if base_med == 0 or np.isnan(base_med):
                ax.set_visible(False); continue
            cur = sub[(sub.degradation == deg) & (sub.metric == metric)]
            if cur.empty:
                ax.set_visible(False); continue
            grouped = cur.groupby("k")["value"].median().sort_index()
            # adiciona ponto k=0 (baseline)
            ks = [0.0] + list(grouped.index)
            vs = [base_med] + list(grouped.values)
            ratio = [v / base_med for v in vs]
            ax.plot(ks, ratio, marker="o", markersize=3, lw=1, color="#37a")
            ax.axhline(1.0, color="#aaa", lw=0.6, ls="--")
            if i == 0:
                ax.set_title(labels_map[metric], fontsize=8)
            if j == 0:
                ax.set_ylabel(deg, fontsize=8)
            ax.tick_params(labelsize=6)
            ax.set_ylim(0, max(2.0, max(ratio) * 1.05))
    plt.tight_layout()
    return fig_b64(fig)


def scorecard(df: pd.DataFrame) -> pd.DataFrame:
    """Para cada (modalidade, métrica, degradação), calcula:
       - sensibilidade = |valor(k_max) - valor(0)| / valor(0)
       - monotonicidade = |corr_spearman(rank(k), value)|
       Score por métrica = média dessas magnitudes nas degradações que ELA
       deveria detectar (heurística por nome).
    """
    rows = []
    for modality in df.modality.unique():
        sub = df[df.modality == modality]
        baseline = sub[sub.degradation == "none"].groupby("metric").value.median()
        for metric in sub.metric.unique():
            for deg in sub.degradation.unique():
                if deg == "none": continue
                cur = sub[(sub.metric == metric) & (sub.degradation == deg)]
                if cur.empty: continue
                med_per_k = cur.groupby("k").value.median().sort_index()
                if len(med_per_k) < 3: continue
                base = baseline.get(metric, np.nan)
                if np.isnan(base) or base == 0:
                    sens = np.nan
                else:
                    sens = abs(med_per_k.iloc[-1] - base) / abs(base)
                # monotonicidade via Spearman ρ entre k e value
                from scipy.stats import spearmanr
                rho, _ = spearmanr(med_per_k.index, med_per_k.values)
                rows.append({
                    "modality": modality, "metric": metric,
                    "degradation": deg,
                    "sensitivity": float(sens) if not np.isnan(sens) else np.nan,
                    "monotonicity": float(abs(rho)) if not np.isnan(rho) else np.nan,
                })
    return pd.DataFrame(rows)


def main():
    df = pd.read_csv(GRID)
    print(f"Grid carregado: {len(df)} linhas")

    sections = []
    for mod in ("rx", "us", "ct", "mri"):
        plot = dose_response_grid(df, mod)
        if plot:
            sections.append(f"""
<h3>{mod.upper()} — dose-resposta</h3>
<p style="font-size:13px;color:#666;">linhas = degradações, colunas = métricas. Eixo Y = razão à baseline (1.0 = sem efeito).</p>
<img src="data:image/png;base64,{plot}" style="max-width:100%;"/>
""")

    sc = scorecard(df)
    sc_html = ""
    if not sc.empty:
        # tabela compacta: pivot com sensibilidade média por (metric × degradation)
        piv = (sc.groupby(["modality", "metric", "degradation"])
                 .sensitivity.mean().unstack(fill_value=np.nan))
        sc_html = f"""
<h3>Scorecard — sensibilidade |Δ/baseline| por degradação</h3>
<p style="font-size:13px;color:#666;">Quanto maior, mais a métrica responde àquela degradação.
Métrica que tem ~0 em uma coluna não detecta aquele tipo de degradação.</p>
{piv.round(2).to_html(classes='tbl', float_format=lambda x: f'{x:.2f}', na_rep='—')}
<h3>Monotonicidade |Spearman| (degradação crescente → métrica monótona?)</h3>
{(sc.groupby(['modality','metric','degradation']).monotonicity.mean()
   .unstack(fill_value=np.nan)
   .round(2).to_html(classes='tbl', float_format=lambda x: f'{x:.2f}', na_rep='—'))}
"""

    n_imgs = df[df.degradation == "none"].file.nunique()
    n_metrics = df.metric.nunique()
    n_degs = df[df.degradation != "none"].degradation.nunique()
    html = f"""
<h2>Degradação controlada — F5</h2>
<div class="legend">
<b>Como funciona:</b> aplicamos {n_degs} tipos de degradação (ruído, blur,
contraste, JPEG, quantização, downup) em 5 níveis k crescentes em
{n_imgs} imagens (subset), recalculamos {n_metrics} métricas em cada
degradação. Mostra como cada métrica reage e flagra quais detectam o quê.
</div>
{''.join(sections)}
{sc_html}
"""
    OUT.write_text(html)
    print(f"OK — {OUT}")


if __name__ == "__main__":
    main()
