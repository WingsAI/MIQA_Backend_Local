"""Métricas CT v2 — slice consistency em volumes.

Como o dataset stroke teve metadados de série anonimizados, agrupamos por:
  pseudo-volume = janela deslizante de N slices consecutivos no mesmo
  diretório original (ordenados por nome numérico).

Métricas por pseudo-volume:
- mean_hu_drift: |Δ μ_volume| pico — quanto μ desvia entre slices vizinhos
- air_sigma_cov: CoV de σ_ar entre slices (estabilidade de ruído)
- slice_corr: mediana Pearson entre slices consecutivos (continuidade anatômica)
- anomaly_pct: % slices > 3σ da média local (flagra slices fora de série)
"""
from __future__ import annotations
import numpy as np


def _ensure_hu(slices: list[np.ndarray]) -> bool:
    """Heurística: HU típica de CT vai de ~-1024 (ar) a +>1000 (osso) ou
    pelo menos contém valores claramente negativos (não [0,1] nem [0,255])."""
    return all(s.min() < -100 for s in slices)


def slice_consistency(slices: list[np.ndarray]) -> dict:
    """Recebe lista de slices 2D em HU (mesmo volume), retorna métricas agregadas.

    slices: list of np.ndarray (H, W) em Hounsfield Units
    Retorna dict de métricas; valores NaN se volume curto (<5 slices).
    """
    n = len(slices)
    if n < 5 or not _ensure_hu(slices):
        return {
            "n_slices": n,
            "mean_hu_drift": float("nan"),
            "air_sigma_cov": float("nan"),
            "slice_corr": float("nan"),
            "anomaly_pct": float("nan"),
            "reason": "volume curto ou não-HU",
        }

    # 1. mean_hu_drift = max |Δ μ_slice|
    mus = np.array([s.mean() for s in slices])
    drift = float(np.abs(np.diff(mus)).max())

    # 2. air_sigma_cov = CoV de σ medido em cantos (proxy ar/edge)
    air_sigmas = []
    for s in slices:
        h, w = s.shape
        c = np.concatenate([s[:32, :32].ravel(), s[:32, -32:].ravel(),
                            s[-32:, :32].ravel(), s[-32:, -32:].ravel()])
        # filtra valores plausíveis de ar
        air = c[c < -500]
        if len(air) > 50:
            air_sigmas.append(float(air.std()))
    if len(air_sigmas) >= 3:
        a = np.array(air_sigmas)
        air_cov = float(a.std() / max(a.mean(), 1e-6))
    else:
        air_cov = float("nan")

    # 3. slice_corr = mediana Pearson entre slices consecutivos
    corrs = []
    for i in range(n - 1):
        a = slices[i].ravel().astype(np.float32)
        b = slices[i + 1].ravel().astype(np.float32)
        if len(a) != len(b):
            continue
        a -= a.mean(); b -= b.mean()
        denom = (a.std() * b.std()) + 1e-9
        corrs.append(float((a * b).mean() / denom))
    slice_corr = float(np.median(corrs)) if corrs else float("nan")

    # 4. anomaly_pct: slices cujo μ desvia >3*MAD da mediana local (excluindo o próprio slice)
    anomalies = 0
    for i in range(n):
        lo, hi = max(0, i - 2), min(n, i + 3)
        local = np.concatenate([mus[lo:i], mus[i+1:hi]])
        if len(local) >= 3:
            med = float(np.median(local))
            mad = float(np.median(np.abs(local - med)))
            # 1.4826 = constante para tornar MAD ≈ σ em distribuição normal
            # exige desvio absoluto > 50 HU E > 3·1.4826·MAD (anti-falso positivo
            # em volumes muito uniformes onde MAD é minúsculo)
            if mad > 0 and abs(mus[i] - med) > max(50.0, 3 * 1.4826 * mad):
                anomalies += 1
    anomaly_pct = anomalies / n * 100

    return {
        "n_slices": n,
        "mean_hu_drift": drift,
        "air_sigma_cov": air_cov,
        "slice_corr": slice_corr,
        "anomaly_pct": float(anomaly_pct),
    }
