"""Métricas específicas de ultrassom (B-mode 2D).

Premissas físicas relevantes:
- Speckle: ruído MULTIPLICATIVO característico de US. SNR_speckle = μ/σ em ROI
  homogênea de tecido. Limite teórico de Rayleigh ≈ 1.91; valores reais em
  tecido bem visualizado ficam ~1.5-3.0.
- Shadowing acústico: regiões verticais escuras "atrás" de estruturas que
  refletem/absorvem o feixe (osso, cálculo). Detectável como faixas verticais
  escuras anômalas no terço inferior da imagem.
- Profundidade útil (DoP): em US, sinal cai com profundidade (atenuação). DoP
  é a profundidade onde μ_local cai pra <30% do μ no terço superior.

Convenção: imagem 2D float [0,1], orientação convencional (sonda no topo,
profundidade aumenta pra baixo).
"""
from __future__ import annotations
import numpy as np
import cv2


def _check(img: np.ndarray) -> np.ndarray:
    assert img.ndim == 2 and img.dtype.kind == "f", "img 2D float esperado"
    return img


def speckle_snr(img: np.ndarray, size: int = 32, k_rois: int = 9,
                sigma_floor: float = 0.005) -> tuple[float, dict]:
    """SNR de speckle = mediana de μ/σ em K ROIs homogêneas válidas.
    Em US, valores ~1.5-3.0 indicam tecido bem visualizado."""
    img = _check(img)
    h, w = img.shape
    rng = np.random.default_rng(42)
    cands = []
    for _ in range(400):
        y = int(rng.integers(0, h - size))
        x = int(rng.integers(0, w - size))
        p = img[y:y+size, x:x+size]
        m, s = float(p.mean()), float(p.std())
        if m < 0.05 or m > 0.95:  # descarta sombra total ou saturação
            continue
        if s < sigma_floor:        # descarta uniforme artificial
            continue
        cands.append((s, m, y, x))
    if not cands:
        return float("nan"), {"n_valid_rois": 0}
    cands.sort()
    chosen = cands[:k_rois]
    snrs = [m / s for s, m, _, _ in chosen]
    return float(np.median(snrs)), {
        "n_valid_rois": len(cands),
        "k_used": len(chosen),
        "snr_min": float(min(snrs)),
        "snr_max": float(max(snrs)),
        "mu_mean": float(np.mean([m for _, m, _, _ in chosen])),
        "sigma_mean": float(np.mean([s for s, _, _, _ in chosen])),
    }


def shadowing_index(img: np.ndarray, n_cols: int = 16) -> tuple[float, dict]:
    """Detecta sombra acústica: faixas verticais com média muito menor que vizinhança.

    Calcula μ por coluna (terço inferior, onde sombra aparece), encontra colunas
    com μ < p10 das demais, retorna fração de colunas suspeitas e a maior
    profundidade da sombra detectada.
    """
    img = _check(img)
    h, w = img.shape
    bottom = img[h*2//3:, :]      # terço inferior
    col_mu = bottom.mean(axis=0)  # média por coluna
    # divide em n_cols blocos pra suavizar
    block_w = max(1, w // n_cols)
    block_mu = np.array([col_mu[i*block_w:(i+1)*block_w].mean()
                         for i in range(n_cols)])
    thr = np.percentile(block_mu, 25) * 0.6  # bem abaixo do p25
    suspects = block_mu < thr
    frac = float(suspects.mean())
    return frac, {
        "n_suspect_blocks": int(suspects.sum()),
        "block_mu_median": float(np.median(block_mu)),
        "block_mu_min": float(block_mu.min()),
        "thr": float(thr),
    }


def depth_of_penetration(img: np.ndarray) -> tuple[float, dict]:
    """Profundidade onde sinal cai pra <30% do topo. Em [0,1] da altura.
    1.0 = sinal preservado até a base; 0.3 = só o topo tem sinal.
    """
    img = _check(img)
    h, _ = img.shape
    # média por linha, suavizada
    row_mu = img.mean(axis=1)
    if h >= 9:
        row_mu = cv2.GaussianBlur(row_mu.astype(np.float32).reshape(-1, 1),
                                   (1, 9), 0).ravel()
    top_mu = row_mu[:h // 5].mean() if h >= 5 else row_mu.mean()
    if top_mu < 1e-6:
        return float("nan"), {"reason": "topo sem sinal"}
    threshold = 0.3 * top_mu
    below = np.where(row_mu < threshold)[0]
    if len(below) == 0:
        dop = 1.0
    else:
        dop = float(below[0] / h)
    return dop, {"top_mu": float(top_mu), "threshold_mu": float(threshold)}


def gain_saturation(img: np.ndarray) -> tuple[float, dict]:
    """Fração de pixels saturados (>0.95) — gain alto demais perde info.
    Inverso de subexposição em RX, mas em US é frequente em ganho mal ajustado."""
    img = _check(img)
    sat = float((img > 0.95).mean() * 100)
    dark = float((img < 0.05).mean() * 100)
    flag = "ok"
    if sat > 8: flag = "gain_too_high"
    elif dark > 60: flag = "gain_too_low"
    return sat, {"saturated_pct": sat, "dark_pct": dark, "flag": flag}


ALL_US_METRICS = {
    "speckle_snr": speckle_snr,
    "shadowing": shadowing_index,
    "depth_of_penetration": depth_of_penetration,
    "gain": gain_saturation,
}


def run_all_us(img: np.ndarray) -> dict:
    out = {}
    for name, fn in ALL_US_METRICS.items():
        v, extra = fn(img)
        out[name] = {"value": v, **extra}
    return out
