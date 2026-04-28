"""Métricas específicas de RM (ressonância magnética).

Premissas (B-mode 2D, slice axial/coronal/sagital):
- MRI tem fundo de ar quase totalmente preto (sinal próximo a 0).
- Anatomia ocupa região central; bordas têm ar.
- "Ghosting" típico: réplica deslocada em N/2 pelo eixo de phase encoding,
  geralmente vertical em axial brain.

Métricas:
1. NEMA SNR — sinal médio em ROI de tecido / σ em ROI de fundo de ar.
2. Ghosting score — energia do sinal em "região fantasma" deslocada FOV/2
   além do background normal.
3. Bias field score — desvio relativo entre 4 cantos da região de tecido
   (B1 inhomogeneity proxy).
4. High-freq motion — energia anômala em alta frequência da FFT do tecido
   (movimento gera pseudo-aliasing).
"""
from __future__ import annotations
import numpy as np
import cv2


def _check(img: np.ndarray) -> np.ndarray:
    assert img.ndim == 2 and img.dtype.kind == "f", "img 2D float esperado"
    return img


def _tissue_mask(img: np.ndarray) -> np.ndarray:
    """Tecido = MAIOR componente conectado acima do percentil 30.
    Ignora ghosts e artefatos pequenos (preserva detecção pelo ghosting_score).
    """
    img = _check(img)
    thr = np.percentile(img, 30)
    binary = (img > thr).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    # NÃO usar MORPH_CLOSE aqui: fecharia gaps entre tecido e fantasma e os fundiria.
    n_comp, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
    if n_comp <= 1:
        return binary.astype(bool)
    # 0 = fundo; pega o maior dos demais
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return (labels == largest)


def nema_snr(img: np.ndarray, size: int = 32) -> tuple[float, dict]:
    """SNR estilo NEMA: μ_tecido / σ_fundo.

    Tecido: pixels dentro da máscara, descartando bordas.
    Fundo:  cantos da imagem, onde só há ar (sem tecido).
    """
    img = _check(img)
    h, w = img.shape
    mask = _tissue_mask(img)
    if mask.sum() < (h * w * 0.05):
        return float("nan"), {"reason": "máscara de tecido pequena"}

    # erosão pra evitar edge effect
    eroded = cv2.erode(mask.astype(np.uint8),
                       cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))).astype(bool)
    if eroded.sum() < (h * w * 0.02):
        eroded = mask
    mu_tissue = float(img[eroded].mean())

    # cantos = 4 quadrados size×size que NÃO sobrepõem máscara de tecido
    cands = []
    for y, x in [(0, 0), (0, w-size), (h-size, 0), (h-size, w-size)]:
        if mask[y:y+size, x:x+size].any():
            continue
        p = img[y:y+size, x:x+size]
        cands.append(float(p.std()))
    if not cands:
        return float("nan"), {"reason": "sem ROI de fundo limpa"}
    sigma_bg = float(np.median(cands))
    if sigma_bg < 1e-6:
        return float("nan"), {"reason": "fundo perfeitamente uniforme"}
    return mu_tissue / sigma_bg, {
        "mu_tissue": mu_tissue, "sigma_bg": sigma_bg,
        "n_bg_rois": len(cands), "tissue_pct": float(eroded.sum() / (h*w) * 100),
    }


def ghosting_score(img: np.ndarray) -> tuple[float, dict]:
    """Detecta ghosting N/2: compara sinal médio numa "faixa fantasma"
    deslocada h/2 acima/abaixo da máscara de tecido vs fundo distante.

    Fantasma alto = energia anormal em região que deveria ser ar.
    """
    img = _check(img)
    mask = _tissue_mask(img)
    h, w = img.shape
    if mask.sum() < (h * w * 0.05):
        return float("nan"), {"reason": "máscara pequena"}

    shift = h // 2
    shifted_up = np.zeros_like(mask)
    shifted_dn = np.zeros_like(mask)
    if shift < h:
        shifted_up[:h - shift] = mask[shift:]
        shifted_dn[shift:] = mask[:h - shift]
    ghost_up = shifted_up & ~mask
    ghost_dn = shifted_dn & ~mask
    bg_mask = ~(mask | shifted_up | shifted_dn)
    if bg_mask.sum() < 100:
        return float("nan"), {"reason": "fundo verdadeiro pequeno"}

    bg_mu = float(img[bg_mask].mean())
    bg_sd = float(img[bg_mask].std())
    if bg_sd < 1e-6:
        return float("nan"), {"reason": "bg sem variação"}

    # SCORE máximo entre os dois lados (ghosting real é direcional)
    scores = []
    for gm in (ghost_up, ghost_dn):
        if gm.sum() >= 100:
            mu = float(img[gm].mean())
            scores.append((mu - bg_mu) / bg_sd)
    if not scores:
        return 0.0, {"reason": "sem região de fantasma utilizável"}
    score_max = float(max(scores))
    return score_max, {
        "score_up": scores[0] if len(scores) > 0 else None,
        "score_dn": scores[1] if len(scores) > 1 else None,
        "bg_mu": bg_mu, "bg_sd": bg_sd,
    }


def bias_field_score(img: np.ndarray, n_blocks: int = 4) -> tuple[float, dict]:
    """B1 inhomogeneity proxy: divide o tecido em n×n blocos, mede CoV das
    médias por bloco. CoV alto = sinal varia espacialmente → bias field forte.
    """
    img = _check(img)
    mask = _tissue_mask(img)
    if mask.sum() < 1000:
        return float("nan"), {"reason": "tecido pequeno"}
    h, w = img.shape
    bh, bw = h // n_blocks, w // n_blocks
    block_mus = []
    for i in range(n_blocks):
        for j in range(n_blocks):
            y0, y1 = i*bh, (i+1)*bh
            x0, x1 = j*bw, (j+1)*bw
            block_mask = mask[y0:y1, x0:x1]
            if block_mask.sum() < 50:
                continue
            block_img = img[y0:y1, x0:x1][block_mask]
            block_mus.append(float(block_img.mean()))
    if len(block_mus) < 4:
        return float("nan"), {"reason": "poucos blocos válidos"}
    a = np.array(block_mus)
    cov = float(a.std() / max(a.mean(), 1e-6))
    return cov, {"n_blocks_used": len(block_mus), "mean_block_mu": float(a.mean())}


def motion_highfreq(img: np.ndarray) -> tuple[float, dict]:
    """Movimento em MRI gera energia anômala em alta freq. Razão entre
    energia em banda alta (>= 0.6·Nyquist) e energia total. Maior = mais movimento."""
    img = _check(img)
    mask = _tissue_mask(img)
    h, w = img.shape
    # FFT só no patch de tecido central (evita borda ar/tecido)
    half_h, half_w = h // 4, w // 4
    central = img[half_h:3*half_h, half_w:3*half_w]
    central = central - central.mean()
    F = np.fft.fft2(central)
    P = np.abs(F) ** 2
    P = np.fft.fftshift(P)
    cy, cx = central.shape[0] // 2, central.shape[1] // 2
    yy, xx = np.mgrid[:central.shape[0], :central.shape[1]]
    r = np.sqrt((yy - cy)**2 + (xx - cx)**2)
    r_max = min(cy, cx)
    high_band = P[(r >= 0.6 * r_max) & (r < r_max)].sum()
    total = P.sum()
    if total < 1e-9:
        return float("nan"), {"reason": "sem energia espectral"}
    return float(high_band / total), {"r_max": int(r_max)}


ALL_MRI_METRICS = {
    "nema_snr": nema_snr,
    "ghosting": ghosting_score,
    "bias_field": bias_field_score,
    "motion_hf": motion_highfreq,
}


def run_all_mri(img: np.ndarray) -> dict:
    out = {}
    for name, fn in ALL_MRI_METRICS.items():
        v, extra = fn(img)
        out[name] = {"value": v, **extra}
    return out
