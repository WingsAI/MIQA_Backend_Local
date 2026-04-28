"""Métricas RX v2 — propostas para autoresearch.

1. NPS radial (Noise Power Spectrum):
   - 2D FFT de ROI homogênea (mean-subtracted), módulo², média radial.
   - Saídas: peak_freq, low_band_power, high_band_power, total_energy.
   - Caracteriza textura do ruído (graininess vs grumos vs banding).

2. Lung-mask SNR:
   - Segmentação heurística do campo pulmonar (regiões escuras no centro,
     longe das bordas).
   - SNR mediana só dentro da máscara → métrica anatomicamente informada.
"""
from __future__ import annotations
import numpy as np
import cv2


def _check(img: np.ndarray) -> np.ndarray:
    assert img.ndim == 2 and img.dtype.kind == "f", "img 2D float esperado"
    return img


# ---------- NPS radial ----------

def nps_radial(img: np.ndarray, roi_size: int = 128, n_bands: int = 5,
               sigma_floor: float = 0.005) -> tuple[float, dict]:
    """NPS radial em ROI homogênea. Retorna fração de energia em alta frequência
    (banda 4/5) — proxy de "graininess" do ruído. ROI ~128 dá frequências [0, 64) cycles/ROI.

    valor retornado = high_band_fraction (0-1)
    extras: peak_freq_bin, total_energy, bands (lista de energia por banda)
    """
    img = _check(img)
    h, w = img.shape
    if h < roi_size or w < roi_size:
        roi_size = min(h, w) // 2 * 2  # próximo par
    rng = np.random.default_rng(42)
    cands = []
    for _ in range(200):
        y = int(rng.integers(0, h - roi_size))
        x = int(rng.integers(0, w - roi_size))
        p = img[y:y+roi_size, x:x+roi_size]
        m, s = float(p.mean()), float(p.std())
        if m < 0.05 or m > 0.95 or s < sigma_floor:
            continue
        cands.append((s, p))
    if not cands:
        return float("nan"), {"reason": "sem ROI homogênea"}
    cands.sort(key=lambda t: t[0])
    # usa as 3 ROIs mais homogêneas e calcula NPS médio (estabiliza)
    nps_avg = None
    for _, p in cands[:3]:
        f = np.fft.fft2(p - p.mean())
        ps = np.abs(f) ** 2
        ps = np.fft.fftshift(ps)
        nps_avg = ps if nps_avg is None else nps_avg + ps
    nps_avg /= 3

    # média radial
    cy, cx = roi_size // 2, roi_size // 2
    yy, xx = np.mgrid[:roi_size, :roi_size]
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    r_max = roi_size // 2
    bins = np.linspace(0, r_max, n_bands + 1)
    band_energy = np.array([
        nps_avg[(r >= bins[i]) & (r < bins[i+1])].sum()
        for i in range(n_bands)
    ])
    total = float(band_energy.sum())
    if total < 1e-9:
        return float("nan"), {"reason": "energia zero"}
    high_frac = float(band_energy[-1] / total)
    # peak freq bin (excluindo DC = banda 0)
    peak_bin = int(np.argmax(band_energy[1:]) + 1)
    return high_frac, {
        "n_rois_used": min(3, len(cands)),
        "peak_band": peak_bin,
        "total_energy": total,
        "bands_norm": [float(e / total) for e in band_energy],
    }


# ---------- Lung mask + SNR ----------

def detect_lung_mask(img: np.ndarray) -> np.ndarray:
    """Heurística: campos pulmonares são regiões escuras (intensidade baixa)
    no centro de uma RX de tórax. Limiar adaptativo + maiores componentes
    centrais.
    """
    img = _check(img)
    h, w = img.shape
    # threshold abaixo do percentil 35 (parte mais escura do tórax)
    thr = np.percentile(img, 35)
    binary = (img < thr).astype(np.uint8)
    # remove borda e ar externo: zona central [10%, 90%]
    margin_y = h // 10
    margin_x = w // 10
    border_mask = np.zeros_like(binary)
    border_mask[margin_y:-margin_y, margin_x:-margin_x] = 1
    binary = binary * border_mask
    # morfologia para limpar
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    # mantém só componentes grandes (>2% da área)
    n_comp, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
    min_area = 0.02 * h * w
    keep = np.zeros_like(binary)
    for k in range(1, n_comp):
        if stats[k, cv2.CC_STAT_AREA] >= min_area:
            keep[labels == k] = 1
    return keep.astype(bool)


def lung_snr(img: np.ndarray, size: int = 48, k_rois: int = 9,
             sigma_floor: float = 0.005) -> tuple[float, dict]:
    """SNR só dentro da máscara pulmonar. Mais informativo que SNR cego."""
    img = _check(img)
    mask = detect_lung_mask(img)
    if mask.sum() < (size * size * 4):  # área mínima
        return float("nan"), {"reason": "lung mask vazia/pequena", "mask_area": int(mask.sum())}
    h, w = img.shape
    rng = np.random.default_rng(42)
    cands = []
    for _ in range(800):
        y = int(rng.integers(0, h - size))
        x = int(rng.integers(0, w - size))
        # ROI inteiramente dentro da máscara pulmonar
        if mask[y:y+size, x:x+size].mean() < 0.95:
            continue
        p = img[y:y+size, x:x+size]
        m, s = float(p.mean()), float(p.std())
        if s < sigma_floor:
            continue
        cands.append((s, m, y, x))
    if not cands:
        return float("nan"), {"reason": "sem ROI homogênea no pulmão",
                              "mask_area": int(mask.sum())}
    cands.sort()
    chosen = cands[:k_rois]
    snrs = [m / s for s, m, _, _ in chosen]
    return float(np.median(snrs)), {
        "n_lung_rois": len(cands),
        "k_used": len(chosen),
        "mask_area_pct": float(mask.sum() / (h * w) * 100),
        "snr_min": float(min(snrs)),
        "snr_max": float(max(snrs)),
        "mu_mean": float(np.mean([m for _, m, _, _ in chosen])),
    }


ALL_RX_V2 = {
    "nps_high_frac": nps_radial,
    "lung_snr": lung_snr,
}


def run_all_rx_v2(img: np.ndarray) -> dict:
    out = {}
    for name, fn in ALL_RX_V2.items():
        v, extra = fn(img)
        out[name] = {"value": v, **extra}
    return out
