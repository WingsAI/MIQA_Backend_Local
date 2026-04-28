"""Scorecard de métricas — decide quais ficam no time titular.

Lê:
  - degradation_grid.csv (sensibilidade + monotonicidade)
  - {rx,us,ct}_quality.csv + v2/_v2 (ortogonalidade)

Calcula 3 dimensões por métrica × modalidade:
  1. responsiveness: |Δvalor(k_max)/baseline| médio nas degradações relevantes
  2. monotonicity:    |Spearman ρ(k, value)| médio
  3. uniqueness:      1 − max(|ρ_spearman| com outras métricas)  (ortogonalidade)

Score final = 0.4·responsiveness_norm + 0.3·monotonicity + 0.3·uniqueness
Decisão (heurística): keep se score >= 0.4, drop_redundant se uniqueness < 0.3,
drop_inert se responsiveness e monotonicity ambos < 0.2.

Saídas:
  miqa/results/metric_scorecard.csv
  miqa/results/_scorecard_section.html  (snippet embutido no consolidado)
"""
from __future__ import annotations
import base64, io
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr

ROOT = Path(__file__).parent.parent
RESULTS = ROOT / "results"
GRID = RESULTS / "degradation_grid.csv"
OUT_CSV = RESULTS / "metric_scorecard.csv"
OUT_HTML = RESULTS / "_scorecard_section.html"


def load_modality_full(mod: str) -> pd.DataFrame:
    """Junta v1 + v2 universal + v2 modalidade num único DF (para ortogonalidade)."""
    paths = [RESULTS / f"{mod}_quality.csv"]
    v2_uni = RESULTS / "v2_metrics.csv"
    df = pd.read_csv(paths[0])
    if v2_uni.exists():
        u = pd.read_csv(v2_uni)
        u = u[u.modality == mod][["file", "niqe", "brisque"]]
        df = df.merge(u, on="file", how="left")
    extra = RESULTS / f"{mod}_v2_metrics.csv"
    if extra.exists():
        ev = pd.read_csv(extra)
        if "file" in ev.columns:  # ct_v2 é per-volume, sem file → ignorar
            df = df.merge(ev, on="file", how="left")
    return df


# Mapeia nome compacto da grid (ex 'rx.snr') para coluna no quality.csv (ex 'rx.snr.value')
def grid_to_csv_col(metric_grid: str) -> str:
    """Converte 'rx.snr' → 'rx.snr.value'; 'v2.niqe' → 'niqe'; 'rx_v2.lung_snr' → 'v2.lung_snr.value'."""
    if metric_grid == "v2.niqe": return "niqe"
    if metric_grid == "v2.brisque": return "brisque"
    if metric_grid.startswith("rx_v2."):
        return "v2." + metric_grid.split(".", 1)[1] + ".value"
    if metric_grid.startswith("us_v2."):
        return "v2." + metric_grid.split(".", 1)[1] + ".value"
    return metric_grid + ".value"


def main():
    grid = pd.read_csv(GRID)
    print(f"Grid: {len(grid)} linhas, {grid.metric.nunique()} métricas, "
          f"{grid.modality.nunique()} modalidades")

    rows = []
    for mod in grid.modality.unique():
        sub = grid[grid.modality == mod]
        baseline = sub[sub.degradation == "none"].groupby("metric").value.median()

        full = load_modality_full(mod)
        # canonicaliza colunas pra Spearman
        for metric in sub.metric.unique():
            base = baseline.get(metric, np.nan)
            # 1. responsiveness
            sens_per_deg = []
            mono_per_deg = []
            for deg in sub.degradation.unique():
                if deg == "none": continue
                cur = sub[(sub.metric == metric) & (sub.degradation == deg)]
                if cur.empty: continue
                med = cur.groupby("k").value.median().sort_index()
                if len(med) < 3: continue
                if not np.isnan(base) and base != 0:
                    sens_per_deg.append(abs(med.iloc[-1] - base) / abs(base))
                rho, _ = spearmanr(med.index, med.values)
                if not np.isnan(rho):
                    mono_per_deg.append(abs(rho))
            responsiveness = float(np.nanmean(sens_per_deg)) if sens_per_deg else np.nan
            monotonicity = float(np.nanmean(mono_per_deg)) if mono_per_deg else np.nan

            # 2. uniqueness (orthogonality) usando o subset real
            csv_col = grid_to_csv_col(metric)
            other_cols = [c for c in full.columns
                          if c != csv_col and c.endswith(".value") or c in ("niqe", "brisque")]
            if csv_col in full.columns:
                self_v = pd.to_numeric(full[csv_col], errors="coerce")
                max_corr = 0.0
                for c in other_cols:
                    if c == csv_col: continue
                    other_v = pd.to_numeric(full[c], errors="coerce")
                    valid = self_v.notna() & other_v.notna()
                    if valid.sum() < 10: continue
                    rho = self_v[valid].corr(other_v[valid], method="spearman")
                    if not np.isnan(rho):
                        max_corr = max(max_corr, abs(rho))
                uniqueness = 1.0 - max_corr
            else:
                uniqueness = np.nan

            rows.append({
                "modality": mod, "metric": metric,
                "responsiveness": responsiveness,
                "monotonicity": monotonicity,
                "uniqueness": uniqueness,
            })

    sc = pd.DataFrame(rows)
    # normaliza responsiveness por modalidade (0-1) — estava em escala arbitrária
    sc["responsiveness_norm"] = sc.groupby("modality")["responsiveness"].transform(
        lambda s: (s.fillna(0) / s.replace([np.inf], np.nan).max()).clip(0, 1)
    )
    sc["score"] = (0.4 * sc["responsiveness_norm"].fillna(0)
                   + 0.3 * sc["monotonicity"].fillna(0)
                   + 0.3 * sc["uniqueness"].fillna(0))

    def decide(row):
        if pd.isna(row["uniqueness"]): return "missing_data"
        if row["uniqueness"] < 0.3: return "drop_redundant"
        if row["responsiveness_norm"] < 0.05 and row["monotonicity"] < 0.4:
            return "drop_inert"
        if row["score"] >= 0.4: return "keep"
        return "review"
    sc["decision"] = sc.apply(decide, axis=1)
    sc = sc.sort_values(["modality", "score"], ascending=[True, False])
    sc.to_csv(OUT_CSV, index=False)
    print(f"\nCSV: {OUT_CSV}  ({len(sc)} entradas)")
    print(sc.groupby("decision").size().to_string())

    # plot
    fig, axes = plt.subplots(1, 3, figsize=(13, 5), dpi=110, sharey=True)
    for ax, mod in zip(axes, ("rx", "us", "ct")):
        m = sc[sc.modality == mod].copy()
        if m.empty:
            ax.set_visible(False); continue
        m = m.sort_values("score")
        colors = {"keep": "#3a7", "drop_redundant": "#c33",
                  "drop_inert": "#999", "review": "#c90", "missing_data": "#ccc"}
        c = [colors[d] for d in m.decision]
        ax.barh(range(len(m)), m["score"], color=c)
        ax.set_yticks(range(len(m)))
        ax.set_yticklabels(m["metric"], fontsize=8)
        ax.set_xlim(0, 1)
        ax.set_title(f"{mod.upper()}", fontsize=11)
        ax.tick_params(labelsize=8)
        ax.set_xlabel("score (0-1)", fontsize=8)
    plt.tight_layout()
    buf = io.BytesIO(); fig.savefig(buf, format="png", bbox_inches="tight"); plt.close(fig)
    plot_b64 = base64.b64encode(buf.getvalue()).decode()

    # HTML snippet
    table_html = sc[["modality", "metric", "responsiveness_norm", "monotonicity",
                      "uniqueness", "score", "decision"]].rename(columns={
        "responsiveness_norm": "respond"
    }).to_html(index=False, classes="tbl",
               float_format=lambda x: f"{x:.2f}", na_rep="—")

    snippet = f"""
<h2>Scorecard de métricas — auto-poda (C)</h2>
<div class="legend">
<b>Score</b> = 0.4·responsiveness_norm + 0.3·monotonicity + 0.3·uniqueness, ∈[0,1]<br>
<b>responsiveness</b>: |Δ valor / baseline| médio nas degradações<br>
<b>monotonicity</b>: |Spearman ρ(k, valor)| médio (a métrica acompanha k crescente?)<br>
<b>uniqueness</b>: 1 − max correlação |ρ| com outras métricas (1 = totalmente nova, 0 = duplicada)<br>
<b>Decisões</b>: <span style="color:#3a7"><b>keep</b></span> (score ≥ 0.4) ·
<span style="color:#c33"><b>drop_redundant</b></span> (uniq < 0.3) ·
<span style="color:#999"><b>drop_inert</b></span> (não responde) ·
<span style="color:#c90"><b>review</b></span> (caso de fronteira)
</div>
<img src="data:image/png;base64,{plot_b64}" style="max-width:100%;"/>
<h3>Tabela completa</h3>
{table_html}
"""
    OUT_HTML.write_text(snippet)
    print(f"HTML: {OUT_HTML}")


if __name__ == "__main__":
    main()
