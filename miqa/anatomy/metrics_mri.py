"""Métricas MRI anatomy-aware — por exame/anatomia.

Todas as funções recebem img: np.ndarray 2D float [0,1] e retornam (valor, dict_extras).
"""
from __future__ import annotations
import numpy as np
import cv2

from miqa.anatomy.metric_registry import register


def _check(img: np.ndarray) -> np.ndarray:
    assert img.ndim == 2 and img.dtype.kind == "f", "img 2D float esperado"
    return img


# ========== MRI BRAIN ==========

@register("mri_brain.scalp_snr")
def mri_brain_scalp_snr(img: np.ndarray) -> tuple[float, dict]:
    """SNR usando escalpo como referencia de ruido (resolve problema de cantos sem ar).
    Escalpo = borda externa da cabeca, tecido com sinal."""
    img = _check(img)
    h, w = img.shape
    # Detecta cabeca (maior componente conectado)
    thr = np.percentile(img, 20)
    head = (img > thr).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(head)
    if n <= 1:
        return float("nan"), {"reason": "no head detected"}
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    head_mask = (labels == largest)
    # Escalpo = borda da cabeca (dilatacao - erosao)
    head_u8 = head_mask.astype(np.uint8)
    dilated = cv2.dilate(head_u8, np.ones((15, 15), np.uint8), iterations=2)
    eroded = cv2.erode(head_u8, np.ones((15, 15), np.uint8), iterations=2)
    scalp = dilated.astype(bool) & ~eroded.astype(bool)
    # Tecido cerebral = interior
    brain = eroded.astype(bool)
    if scalp.sum() < 50 or brain.sum() < 50:
        return float("nan"), {"reason": "scalp or brain too small"}
    mu_brain = float(img[brain].mean())
    sigma_scalp = float(img[scalp].std())
    if sigma_scalp < 1e-6:
        return float("nan"), {"reason": "scalp uniform"}
    snr = mu_brain / sigma_scalp
    return float(snr), {
        "brain_mu": mu_brain,
        "scalp_sigma": sigma_scalp,
        "scalp_area_pct": float(scalp.mean() * 100),
    }


@register("mri_brain.wm_gm_ratio")
def mri_brain_wm_gm_ratio(img: np.ndarray) -> tuple[float, dict]:
    """Relacao de intensidade substancia branca / cinza.
    Esperado ~1.3-1.8 em T1. Fora dessa faixa = problema tecnico ou patologia."""
    img = _check(img)
    h, w = img.shape
    # Centro do cerebro
    center = img[h//4:3*h//4, w//4:3*w//4]
    # Histograma bimodal: GM (escuro) e WM (claro)
    p33 = np.percentile(center, 33)
    p67 = np.percentile(center, 67)
    gm_mask = (center >= p33) & (center <= (p33 + p67)/2)
    wm_mask = center >= p67
    if gm_mask.sum() < 100 or wm_mask.sum() < 100:
        return float("nan"), {"reason": "insufficient WM/GM regions"}
    mu_gm = float(center[gm_mask].mean())
    mu_wm = float(center[wm_mask].mean())
    if mu_gm < 1e-6:
        return float("nan"), {"reason": "GM signal too low"}
    ratio = mu_wm / mu_gm
    return float(ratio), {
        "wm_mu": mu_wm,
        "gm_mu": mu_gm,
        "wm_gm_ratio": float(ratio),
        "expected_range": "1.3-1.8 (T1)",
    }


@register("mri_brain.flow_artifact_score")
def mri_brain_flow_artifact_score(img: np.ndarray) -> tuple[float, dict]:
    """Detecta artefato de fluxo em vasos/CSF: linhas bright em estruturas fluidas.
    Procura padroes de aliasing em regioes de CSF."""
    img = _check(img)
    h, w = img.shape
    # CSF = regioes escuras no centro (ventriculos)
    center = img[h//3:2*h//3, w//3:2*w//3]
    dark_thr = np.percentile(center, 25)
    csf_mask = (center < dark_thr).astype(np.uint8)
    # Componentes
    n, labels, stats, _ = cv2.connectedComponentsWithStats(csf_mask)
    if n <= 1:
        return 0.0, {"reason": "no CSF detected", "score": 0.0}
    # Artefato = brilho anomalo dentro ou ao redor de CSF
    csf_u8 = (labels > 0).astype(np.uint8)
    dilated = cv2.dilate(csf_u8, np.ones((5, 5), np.uint8), iterations=2)
    artifact_zone = dilated.astype(bool) & ~(labels > 0)
    if artifact_zone.sum() == 0:
        return 0.0, {"score": 0.0}
    # Bright pixels no artifact zone
    bright_thr = np.percentile(center, 75)
    bright_artifact = artifact_zone & (center > bright_thr)
    score = float(bright_artifact.mean())
    return float(score), {
        "flow_artifact_score": score,
        "artifact_zone_pct": float(artifact_zone.mean() * 100),
    }


# ========== MRI KNEE ==========

@register("mri_knee.cartilage_homogeneity")
def mri_knee_cartilage_homogeneity(img: np.ndarray) -> tuple[float, dict]:
    """Homogeneidade da cartilagem articular: variação de sinal deve ser baixa.
    Cartilagem = regiao intermediaria entre osso (claro) e fluido (escuro)."""
    img = _check(img)
    h, w = img.shape
    # Regiao central (joelho)
    center = img[h//4:3*h//4, w//4:3*w//4]
    # Cartilagem = valores intermediarios
    p30 = np.percentile(center, 30)
    p70 = np.percentile(center, 70)
    cartilage = (center > p30) & (center < p70)
    if cartilage.sum() < 100:
        return float("nan"), {"reason": "insufficient cartilage"}
    mu = float(center[cartilage].mean())
    sigma = float(center[cartilage].std())
    if mu < 1e-6:
        return float("nan"), {"reason": "cartilage signal too low"}
    cov = sigma / mu
    score = max(0, 1 - cov * 3)
    return float(score), {
        "cartilage_cov": cov,
        "cartilage_mu": mu,
        "homogeneity_score": float(score),
    }


@register("mri_knee.meniscus_contrast")
def mri_knee_meniscus_contrast(img: np.ndarray) -> tuple[float, dict]:
    """Contraste entre menisco (escuro) e fluido articular (claro).
    Menisco deve ser visivelmente escuro contra fluido brilhante."""
    img = _check(img)
    h, w = img.shape
    center = img[h//4:3*h//4, w//4:3*w//4]
    # Menisco = escuro, triangular
    meniscus = center < np.percentile(center, 30)
    fluid = center > np.percentile(center, 70)
    if meniscus.sum() < 50 or fluid.sum() < 50:
        return float("nan"), {"reason": "insufficient regions"}
    mu_men = float(center[meniscus].mean())
    mu_fluid = float(center[fluid].mean())
    contrast = abs(mu_fluid - mu_men)
    return float(contrast), {
        "meniscus_mu": mu_men,
        "fluid_mu": mu_fluid,
        "contrast": float(contrast),
    }


# ========== MRI SPINE ==========

@register("mri_spine.disc_vertebra_ratio")
def mri_spine_disc_vertebra_ratio(img: np.ndarray) -> tuple[float, dict]:
    """Relacao sinal disco/vertebra: degeneracao = queda de contraste.
    Disco = escuro (nucleo), vertebra = intermediario."""
    img = _check(img)
    h, w = img.shape
    # Coluna vertical central
    center = img[:, w//3:2*w//3]
    # Perfil vertical
    profile = center.mean(axis=1)
    # Encontra picos (vertebras) e vales (discos)
    from scipy.signal import find_peaks
    peaks, _ = find_peaks(profile, distance=h//10, prominence=0.05)
    valleys, _ = find_peaks(-profile, distance=h//10, prominence=0.05)
    if len(peaks) < 2 or len(valleys) < 1:
        return float("nan"), {"reason": "insufficient vertebrae/discs"}
    # Media dos picos e vales
    peak_mean = float(profile[peaks].mean())
    valley_mean = float(profile[valleys].mean())
    if valley_mean < 1e-6:
        return float("nan"), {"reason": "disc signal too low"}
    ratio = peak_mean / valley_mean
    return float(ratio), {
        "vertebra_mean": peak_mean,
        "disc_mean": valley_mean,
        "ratio": float(ratio),
        "n_vertebrae": len(peaks),
        "n_discs": len(valleys),
    }


# ========== MRI ABDOMEN (DWI) ==========

@register("mri_abdomen.adc_consistency")
def mri_abdomen_adc_consistency(img: np.ndarray) -> tuple[float, dict]:
    """Consistencia de valores ADC em regiao hepatica.
    ADC deve ser homogeneo no figado. Alta variancia = artefato ou patologia."""
    img = _check(img)
    h, w = img.shape
    # Figado = regiao central direita (aproximacao)
    liver = img[h//4:3*h//4, :w//2]
    # Valores ADC tipicos: 1.0-1.5 x10^-3 mm2/s
    # Na imagem normalizada, procuramos regiao de intensidade media
    p30 = np.percentile(liver, 30)
    p70 = np.percentile(liver, 70)
    adc_mask = (liver > p30) & (liver < p70)
    if adc_mask.sum() < 100:
        return float("nan"), {"reason": "insufficient liver region"}
    adc_values = liver[adc_mask]
    mu = float(adc_values.mean())
    sigma = float(adc_values.std())
    if mu < 1e-6:
        return float("nan"), {"reason": "ADC signal too low"}
    cov = sigma / mu
    score = max(0, 1 - cov * 3)
    return float(score), {
        "adc_cov": cov,
        "adc_mean": mu,
        "consistency_score": float(score),
    }
