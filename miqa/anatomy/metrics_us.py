"""Métricas US anatomy-aware — por exame/anatomia.

Todas as funções recebem img: np.ndarray 2D float [0,1] e retornam (valor, dict_extras).
"""
from __future__ import annotations
import numpy as np
import cv2

from miqa.anatomy.metric_registry import register


def _check(img: np.ndarray) -> np.ndarray:
    assert img.ndim == 2 and img.dtype.kind == "f", "img 2D float esperado"
    return img


# ========== US ABDOMEN/LIVER ==========

@register("us_abdomen.liver_snr")
def us_abdomen_liver_snr(img: np.ndarray) -> tuple[float, dict]:
    """SNR em ROI homogenea de figado (exclui vasos).
    Figado = maior componente conectado com intensidade media-alta no centro."""
    img = _check(img)
    h, w = img.shape
    # Centro da imagem
    center = img[h//4:3*h//4, w//4:3*w//4]
    # Threshold para tecido
    thr = np.percentile(center, 40)
    tissue = (img > thr).astype(np.uint8)
    # Maior componente
    n, labels, stats, _ = cv2.connectedComponentsWithStats(tissue)
    if n <= 1:
        return float("nan"), {"reason": "no tissue detected"}
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    liver_mask = (labels == largest)
    # Exclui vasos escuros dentro do figado
    liver_img = img.copy()
    liver_img[~liver_mask] = 1.0
    vessel_thr = np.percentile(liver_img[liver_mask], 20)
    parenchyma = liver_mask & (img > vessel_thr)
    if parenchyma.sum() < 100:
        return float("nan"), {"reason": "insufficient parenchyma"}
    mu = float(img[parenchyma].mean())
    sigma = float(img[parenchyma].std())
    if sigma < 1e-6:
        return float("nan"), {"reason": "uniform parenchyma"}
    return mu / sigma, {
        "liver_area_pct": float(liver_mask.mean() * 100),
        "vessel_excluded": True,
        "parenchyma_mu": mu,
    }


@register("us_abdomen.vessel_shadow_ratio")
def us_abdomen_vessel_shadow_ratio(img: np.ndarray) -> tuple[float, dict]:
    """Distingue sombra fisiologica (apos vaso) vs patologica.
    Sombra apos vaso circular = fisiologica. Sombra linear larga = patologica."""
    img = _check(img)
    h, w = img.shape
    # Detectar sombras (regioes escuras no terco inferior)
    bottom = img[2*h//3:, :]
    dark_thr = np.percentile(bottom, 25)
    shadow = (bottom < dark_thr).astype(np.uint8)
    # Propriedades dos componentes
    n, labels, stats, _ = cv2.connectedComponentsWithStats(shadow)
    if n <= 1:
        return 0.0, {"reason": "no shadow detected", "ratio": 0.0}
    # Analisa formato: vessel shadow = estreita e alta, pathological = larga
    ratios = []
    for k in range(1, n):
        width = stats[k, cv2.CC_STAT_WIDTH]
        height = stats[k, cv2.CC_STAT_HEIGHT]
        if height > 20:
            ratios.append(width / max(height, 1))
    if not ratios:
        return 0.0, {"reason": "no valid shadows", "ratio": 0.0}
    avg_ratio = float(np.mean(ratios))
    # Ratio < 0.5 = sombra de vaso (boa), > 1.0 = sombra patologica
    score = max(0, 1 - avg_ratio)
    return float(score), {
        "avg_width_height_ratio": avg_ratio,
        "n_shadows": len(ratios),
        "shadow_type": "vessel" if avg_ratio < 0.5 else "pathological",
    }


# ========== US OBSTETRIC ==========

@register("us_obstetric.gestational_sac_contrast")
def us_obstetric_gestational_sac_contrast(img: np.ndarray) -> tuple[float, dict]:
    """Contraste entre saco gestacional (escuro) e parede uterina (clara).
    Mede qualidade da visualizacao da cavidade gestacional."""
    img = _check(img)
    h, w = img.shape
    # Centro da imagem (saco gestacional tipicamente central)
    center = img[h//4:3*h//4, w//4:3*w//4]
    # Detectar saco (regiao escura circular)
    dark_thr = np.percentile(center, 30)
    sac_mask = (center <= dark_thr).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(sac_mask)
    if n <= 1:
        return float("nan"), {"reason": "no gestational sac detected"}
    # Maior componente escuro
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    sac = (labels == largest)
    # Parede = anel ao redor do saco
    sac_uint8 = sac.astype(np.uint8)
    dilated = cv2.dilate(sac_uint8, np.ones((5, 5), np.uint8), iterations=2)
    wall = dilated.astype(bool) & ~sac
    if sac.sum() < 50 or wall.sum() < 50:
        return float("nan"), {"reason": "sac or wall too small"}
    mu_sac = float(center[sac].mean())
    mu_wall = float(center[wall].mean())
    contrast = abs(mu_wall - mu_sac)
    return float(contrast), {
        "sac_mu": mu_sac,
        "wall_mu": mu_wall,
        "contrast": float(contrast),
        "sac_area_px": int(sac.sum()),
    }


@register("us_obstetric.amniotic_fluid_uniformity")
def us_obstetric_amniotic_fluid_uniformity(img: np.ndarray) -> tuple[float, dict]:
    """Uniformidade do liquido amniotico (deve ser homogeneo e escuro).
    Alta variancia = particulado/ecogenico (possivel sangue/debris)."""
    img = _check(img)
    h, w = img.shape
    # Regiao central escura (liquido)
    center = img[h//4:3*h//4, w//4:3*w//4]
    dark_thr = np.percentile(center, 35)
    fluid_mask = center < dark_thr
    if fluid_mask.sum() < 100:
        return float("nan"), {"reason": "insufficient fluid region"}
    fluid = center[fluid_mask]
    mu = float(fluid.mean())
    sigma = float(fluid.std())
    if mu < 1e-6:
        return float("nan"), {"reason": "fluid too dark"}
    cov = sigma / mu
    # CoV baixo = uniforme (bom). CoV alto = particulado (ruim)
    score = max(0, 1 - cov * 5)  # normaliza
    return float(score), {
        "fluid_cov": cov,
        "fluid_mu": mu,
        "fluid_area_pct": float(fluid_mask.mean() * 100),
    }


# ========== US VASCULAR ==========

@register("us_vascular.vessel_filling_index")
def us_vascular_vessel_filling_index(img: np.ndarray) -> tuple[float, dict]:
    """Indice de preenchimento do vaso na imagem B-mode.
    Vaso = regiao escura tubular. Mede % da area do vaso vs total."""
    img = _check(img)
    h, w = img.shape
    # Vasos = regioes escuras alongadas
    dark_thr = np.percentile(img, 30)
    vessels = (img < dark_thr).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(vessels)
    if n <= 1:
        return float("nan"), {"reason": "no vessels detected"}
    # Seleciona componentes alongados (altura > 3x largura)
    vessel_areas = []
    for k in range(1, n):
        width = stats[k, cv2.CC_STAT_WIDTH]
        height = stats[k, cv2.CC_STAT_HEIGHT]
        area = stats[k, cv2.CC_STAT_AREA]
        if height > width * 2 and area > 50:
            vessel_areas.append(area)
    if not vessel_areas:
        return float("nan"), {"reason": "no elongated vessels"}
    total_vessel = sum(vessel_areas)
    filling = total_vessel / (h * w)
    return float(filling), {
        "vessel_area_pct": filling * 100,
        "n_vessels": len(vessel_areas),
        "total_vessel_px": total_vessel,
    }


# ========== US MSK ==========

@register("us_msk.fiber_orientation")
def us_msk_fiber_orientation(img: np.ndarray) -> tuple[float, dict]:
    """Mede orientacao das fibras musculares via gradiente local.
    Retorna CoV da orientacao (baixo = fibras paralelas, bom)."""
    img = _check(img)
    h, w = img.shape
    # Gradiente
    gx = cv2.Sobel((img * 255).astype(np.uint8), cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel((img * 255).astype(np.uint8), cv2.CV_64F, 0, 1, ksize=3)
    # Orientacao
    orientation = np.arctan2(gy, gx)
    # Apenas regioes com textura (alto gradiente)
    mag = np.sqrt(gx**2 + gy**2)
    mask = mag > np.percentile(mag, 70)
    if mask.sum() < 100:
        return float("nan"), {"reason": "insufficient texture"}
    ori_values = orientation[mask]
    # CoV da orientacao (wrap around pi)
    # Usa statistica circular
    sin_sum = float(np.sin(ori_values).mean())
    cos_sum = float(np.cos(ori_values).mean())
    r = np.sqrt(sin_sum**2 + cos_sum**2)
    # r proximo de 1 = orientacao consistente, proximo de 0 = aleatorio
    return float(r), {
        "orientation_consistency": float(r),
        "n_pixels": int(mask.sum()),
    }


@register("us_msk.tendon_fibril_score")
def us_msk_tendon_fibril_score(img: np.ndarray) -> tuple[float, dict]:
    """Score de fibrilacao tendinea: padrao fibrilar regular e intenso.
    Mede periodicitade da textura via autocorrelacao."""
    img = _check(img)
    h, w = img.shape
    # ROI central
    roi = img[h//4:3*h//4, w//4:3*w//4]
    # Autocorrelacao
    f = np.fft.fft2(roi - roi.mean())
    ac = np.abs(np.fft.ifft2(f * np.conj(f))).real
    ac = np.fft.fftshift(ac)
    ac /= ac.max() + 1e-12
    # Linha horizontal (fibras tendineas tipicamente horizontais)
    cy, cx = ac.shape[0] // 2, ac.shape[1] // 2
    h_line = ac[cy, cx:cx+20]
    # Picos periodicos = fibras regulares
    if len(h_line) < 5:
        return float("nan"), {"reason": "roi too small"}
    # Diferenca de picos
    peaks = np.diff(h_line)
    periodicity = float(np.abs(peaks).mean())
    score = min(1.0, periodicity * 5)
    return float(score), {
        "periodicity": periodicity,
        "fibril_score": float(score),
    }


# ========== US CARDIAC ==========

@register("us_cardiac.acoustic_window_index")
def us_cardiac_acoustic_window_index(img: np.ndarray) -> tuple[float, dict]:
    """Indice de janela acustica: area sem artefato de costela / area total.
    Janela boa = grande area livre de artefatos."""
    img = _check(img)
    h, w = img.shape
    # Artefatos de costela = sombras verticais escuras no topo
    top = img[:h//3, :]
    col_mean = top.mean(axis=0)
    # Colunas com sombra = valores muito baixos
    shadow_thr = np.percentile(col_mean, 25) * 0.5
    shadow_cols = col_mean < shadow_thr
    shadow_frac = float(shadow_cols.mean())
    # Janela = 1 - sombra
    window = 1 - shadow_frac
    return float(window), {
        "acoustic_window_pct": window * 100,
        "shadow_columns_pct": shadow_frac * 100,
    }


@register("us_cardiac.chamber_contrast")
def us_cardiac_chamber_contrast(img: np.ndarray) -> tuple[float, dict]:
    """Contraste entre camaras cardiacas (escuras, sangue) e miocardio (claro).
    Mede diferenca de intensidade entre regioes escuras centrais e bordas."""
    img = _check(img)
    h, w = img.shape
    # Centro (camaras)
    center = img[h//3:2*h//3, w//3:2*w//3]
    # Miocardio = anel ao redor
    center_mask = np.zeros_like(img, dtype=bool)
    center_mask[h//3:2*h//3, w//3:2*w//3] = True
    # Dilata para pegar miocardio
    center_u8 = center_mask.astype(np.uint8)
    dilated = cv2.dilate(center_u8, np.ones((15, 15), np.uint8), iterations=2)
    myocardium = dilated.astype(bool) & ~center_mask
    if center.size == 0 or myocardium.sum() < 50:
        return float("nan"), {"reason": "insufficient regions"}
    mu_chamber = float(center.mean())
    mu_myo = float(img[myocardium].mean())
    contrast = abs(mu_myo - mu_chamber)
    return float(contrast), {
        "chamber_mu": mu_chamber,
        "myocardium_mu": mu_myo,
        "contrast": float(contrast),
    }
