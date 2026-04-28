"""Métricas específicas de RX (radiografia projecional).

Premissas:
- input é float32 [0,1] (caller já tratou MONOCHROME1 inversion + normalização).
- ROIs são patches NxN; usamos automáticos (homogêneo via low-variance + lung/mediastinum heurístico).
  Para uso clínico real isso seria dado por segmentação. Aqui é proxy reproduzível.

Cada métrica retorna (valor, dict_extra).
"""
from __future__ import annotations
import numpy as np
import cv2


def _check(img: np.ndarray) -> np.ndarray:
    assert img.ndim == 2 and img.dtype.kind == "f", "img 2D float esperado"
    return img


def find_homogeneous_roi(img: np.ndarray, size: int = 64, n_candidates: int = 200,
                         seed: int = 42) -> tuple[int, int]:
    """Acha o patch NxN com menor desvio padrão local — proxy de região homogênea
    (típico: mediastino ou tecido mole sem bordas)."""
    img = _check(img)
    rng = np.random.default_rng(seed)
    h, w = img.shape
    best = (np.inf, (0, 0))
    for _ in range(n_candidates):
        y = rng.integers(0, h - size)
        x = rng.integers(0, w - size)
        s = float(img[y:y+size, x:x+size].std())
        # filtra ROIs cuja média está saturada (preto ou branco puro)
        m = float(img[y:y+size, x:x+size].mean())
        if m < 0.05 or m > 0.95:
            continue
        if s < best[0]:
            best = (s, (y, x))
    return best[1]


def snr_homogeneous(img: np.ndarray, size: int = 64, k_rois: int = 9,
                    sigma_floor: float = 0.005) -> tuple[float, dict]:
    """SNR robusto = mediana de μ/σ em K ROIs homogêneas (top-K mais baixas σ).

    sigma_floor evita explosão por ROI artificialmente uniforme (área saturada
    ou comprimida JPEG sem ruído real). ROIs com σ < floor são descartadas.
    Retorna NaN quando nenhuma ROI válida existe.
    """
    img = _check(img)
    h, w = img.shape
    rng = np.random.default_rng(42)
    cands = []  # (sigma, mu, y, x)
    for _ in range(400):
        y = int(rng.integers(0, h - size))
        x = int(rng.integers(0, w - size))
        p = img[y:y+size, x:x+size]
        m, s = float(p.mean()), float(p.std())
        if m < 0.05 or m > 0.95:  # descarta saturado
            continue
        if s < sigma_floor:        # descarta uniforme demais (artefato)
            continue
        cands.append((s, m, y, x))
    if not cands:
        return float("nan"), {"n_valid_rois": 0, "size": size}
    cands.sort()  # menor σ primeiro = ROIs mais homogêneas
    chosen = cands[:k_rois]
    snrs = [m / s for s, m, _, _ in chosen]
    snr_med = float(np.median(snrs))
    return snr_med, {
        "n_valid_rois": len(cands),
        "k_used": len(chosen),
        "size": size,
        "snr_min": float(np.min(snrs)),
        "snr_max": float(np.max(snrs)),
        "mu_mean": float(np.mean([m for _, m, _, _ in chosen])),
        "sigma_mean": float(np.mean([s for s, _, _, _ in chosen])),
    }


def cnr_dark_bright(img: np.ndarray, size: int = 64) -> tuple[float, dict]:
    """CNR entre ROI escura (top-1% candidatos com menor média) e ROI clara (top-1% com maior média),
    ambas homogêneas. Proxy de contraste tecido/ar ou lesão/fundo.

    CNR = |μ_b - μ_d| / sqrt((σ_b² + σ_d²) / 2)
    """
    img = _check(img)
    h, w = img.shape
    rng = np.random.default_rng(42)
    cands = []
    for _ in range(400):
        y = rng.integers(0, h - size)
        x = rng.integers(0, w - size)
        p = img[y:y+size, x:x+size]
        cands.append((float(p.mean()), float(p.std()), int(y), int(x)))
    cands.sort()  # por mu
    # ROI escura: pega o de menor mu com sigma baixo (homogêneo)
    dark = min(cands[:40], key=lambda t: t[1])
    bright = min(cands[-40:], key=lambda t: t[1])
    mu_d, sd_d = dark[0], dark[1]
    mu_b, sd_b = bright[0], bright[1]
    cnr = abs(mu_b - mu_d) / max(np.sqrt((sd_b**2 + sd_d**2) / 2), 1e-6)
    return float(cnr), {
        "dark": {"mu": mu_d, "sigma": sd_d, "xy": (dark[3], dark[2])},
        "bright": {"mu": mu_b, "sigma": sd_b, "xy": (bright[3], bright[2])},
    }


def exposure_proxy(img: np.ndarray) -> tuple[float, dict]:
    """Proxy de exposure index: mediana da intensidade.
    Em RX:
      - mediana muito alta (>0.7) → superexposto (filme/detector saturado)
      - mediana muito baixa (<0.2) → subexposto (ruidoso, pouco sinal)
      - faixa ideal: 0.3-0.6
    """
    img = _check(img)
    med = float(np.median(img))
    p5 = float(np.percentile(img, 5))
    p95 = float(np.percentile(img, 95))
    if med < 0.2:
        flag = "underexposed"
    elif med > 0.7:
        flag = "overexposed"
    else:
        flag = "ok"
    return med, {"p5": p5, "p95": p95, "flag": flag}


def edge_sharpness(img: np.ndarray) -> tuple[float, dict]:
    """Nitidez via percentil 99 da magnitude do gradiente Sobel — peak edge strength.
    Robusto a imagens onde a maioria dos pixels tem gradiente ≈0 (a média seria diluída).
    Cai com blur, sobe com bordas nítidas."""
    img = _check(img)
    g = (img * 255).astype(np.uint8)
    gx = cv2.Sobel(g, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_64F, 0, 1, ksize=3)
    mag = np.sqrt(gx**2 + gy**2)
    p99 = float(np.percentile(mag, 99))
    return p99, {"p99": p99, "p999": float(np.percentile(mag, 99.9))}


ALL_RX_METRICS = {
    "snr": snr_homogeneous,
    "cnr": cnr_dark_bright,
    "exposure": exposure_proxy,
    "edge_sharpness": edge_sharpness,
}


def run_all_rx(img: np.ndarray) -> dict:
    out = {}
    for name, fn in ALL_RX_METRICS.items():
        v, extra = fn(img)
        out[name] = {"value": v, **extra}
    return out
