"""Métricas US v2 — autoresearch.

1. Speckle anisotropy:
   Speckle isotrópico (sonda perpendicular ao tecido) tem auto-correlação
   espacial radialmente simétrica. Sonda inclinada / má acoplação produz
   speckle alongado em uma direção.
   Métrica: razão entre raio de auto-correlação horizontal vs vertical.
   Valor ~1.0 = isotrópico (bom). Valor longe de 1 = anisotropia.

2. Lateral resolution proxy:
   Em ROI homogênea sem speckle alongado, computamos largura média da PSF
   pela autocorrelação. Aproxima FWHM do feixe lateral.

3. TGC consistency:
   Time-Gain-Compensation deveria normalizar média de intensidade ao longo
   da profundidade. Variação grande de μ-por-linha sugere TGC mal ajustado.
"""
from __future__ import annotations
import numpy as np
import cv2


def _check(img: np.ndarray) -> np.ndarray:
    assert img.ndim == 2 and img.dtype.kind == "f", "img 2D float esperado"
    return img


def _find_speckle_roi(img: np.ndarray, size: int = 96, n_cands: int = 200,
                     sigma_floor: float = 0.01) -> tuple[int, int] | None:
    """Acha ROI homogênea grande pra autocorrelação."""
    h, w = img.shape
    if h < size or w < size:
        return None
    rng = np.random.default_rng(42)
    best = (0.0, None)  # maximiza σ (rico em speckle) com mu central
    for _ in range(n_cands):
        y = int(rng.integers(0, h - size))
        x = int(rng.integers(0, w - size))
        p = img[y:y+size, x:x+size]
        m, s = float(p.mean()), float(p.std())
        if m < 0.15 or m > 0.85:
            continue
        if s < sigma_floor:
            continue
        # critério: alto σ (textura presente) + sem gradiente médio (não cruza borda)
        gx = float(np.abs(np.diff(p.mean(axis=0))).mean())
        gy = float(np.abs(np.diff(p.mean(axis=1))).mean())
        score = s - 5 * (gx + gy)  # penaliza gradiente direcional
        if score > best[0]:
            best = (score, (y, x))
    return best[1]


def _autocorr2d(patch: np.ndarray) -> np.ndarray:
    """Auto-correlação 2D normalizada via FFT."""
    p = patch - patch.mean()
    F = np.fft.fft2(p)
    A = np.fft.ifft2(F * np.conj(F)).real
    A = np.fft.fftshift(A)
    A /= A.max() + 1e-12
    return A


def speckle_anisotropy(img: np.ndarray, size: int = 96) -> tuple[float, dict]:
    """Razão raio_horizontal / raio_vertical da auto-correlação. ~1.0 = isotrópico."""
    img = _check(img)
    roi = _find_speckle_roi(img, size=size)
    if roi is None:
        return float("nan"), {"reason": "sem ROI speckle"}
    y, x = roi
    p = img[y:y+size, x:x+size]
    A = _autocorr2d(p)
    cy, cx = size // 2, size // 2
    # raio onde A cai abaixo de 0.5 (FWHM) ao longo de cada eixo
    h_line = A[cy, cx:]      # da origem para a direita
    v_line = A[cy:, cx]      # da origem para baixo
    def fwhm_radius(line):
        below = np.where(line < 0.5)[0]
        return int(below[0]) if len(below) else len(line)
    rh = fwhm_radius(h_line)
    rv = fwhm_radius(v_line)
    if rv == 0 or rh == 0:
        return float("nan"), {"reason": "FWHM=0", "rh": rh, "rv": rv}
    ratio = max(rh, rv) / min(rh, rv)  # >= 1.0; 1.0 = isotrópico
    return float(ratio), {
        "rh_px": rh, "rv_px": rv,
        "roi_xy": (int(x), int(y)),
        "axis_long": "horizontal" if rh > rv else "vertical",
    }


def lateral_resolution_proxy(img: np.ndarray, size: int = 192) -> tuple[float, dict]:
    """FWHM horizontal sub-pixel da auto-correlação — proxy de resolução lateral.
    Menor = mais resolução (PSF mais estreita).

    Mudanças vs v1: ROI 192 (vs 96) e interpolação linear pra FWHM sub-pixel.
    Flag 'saturated=True' quando autocorrelação não cai abaixo de 0.5 dentro
    da meia-largura disponível (raro; significa decorrelação lentíssima).
    """
    img = _check(img)
    # tenta size=192, depois 128, depois 96 conforme tamanho da imagem
    for try_size in (size, 128, 96):
        roi = _find_speckle_roi(img, size=try_size)
        if roi is not None:
            size = try_size
            break
    if roi is None:
        return float("nan"), {"reason": "sem ROI speckle"}
    y, x = roi
    p = img[y:y+size, x:x+size]
    A = _autocorr2d(p)
    cy, cx = size // 2, size // 2
    h_line = A[cy, cx:]   # linha de autocorrelação para a direita
    half = 0.5
    saturated = False
    below_idx = np.where(h_line < half)[0]
    if len(below_idx) == 0:
        # autocorrelação não cai abaixo de 0.5: PSF mais larga que a meia-ROI
        return float(len(h_line)), {"roi_xy": (int(x), int(y)), "size": size,
                                     "saturated": True}
    i = int(below_idx[0])
    if i == 0:
        fwhm = 0.0
    else:
        # interp linear entre h_line[i-1] (>=0.5) e h_line[i] (<0.5)
        v0, v1 = h_line[i-1], h_line[i]
        denom = (v0 - v1) if (v0 - v1) > 1e-9 else 1e-9
        frac = (v0 - half) / denom
        fwhm = (i - 1) + frac
    return float(fwhm), {"roi_xy": (int(x), int(y)), "size": size,
                          "saturated": False, "fwhm_frac_size": fwhm / (size / 2)}


def tgc_consistency(img: np.ndarray) -> tuple[float, dict]:
    """Coeficiente de variação da média por linha (na metade central horizontal).
    Bom TGC: μ aproximadamente constante com profundidade → CoV baixo.
    """
    img = _check(img)
    h, w = img.shape
    central = img[:, w//4:3*w//4]   # ignora margens (sonda reta)
    row_mu = central.mean(axis=1)
    # ignora topo (anel sem sinal) e base (atenuação total)
    cut_top = int(0.05 * h)
    cut_bot = int(0.95 * h)
    profile = row_mu[cut_top:cut_bot]
    mu = float(profile.mean())
    sd = float(profile.std())
    if mu < 1e-6:
        return float("nan"), {"reason": "sinal médio zero"}
    cov = sd / mu
    return float(cov), {"mu_profile": float(mu), "sd_profile": float(sd)}


ALL_US_V2 = {
    "speckle_anisotropy": speckle_anisotropy,
    "lateral_resolution_px": lateral_resolution_proxy,
    "tgc_cov": tgc_consistency,
}


def run_all_us_v2(img: np.ndarray) -> dict:
    out = {}
    for name, fn in ALL_US_V2.items():
        v, extra = fn(img)
        out[name] = {"value": v, **extra}
    return out
