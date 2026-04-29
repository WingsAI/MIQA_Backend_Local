"""Métricas CT anatomy-aware — por exame/anatomia.

Todas as funções recebem img: np.ndarray 2D float [0,1] ou HU + hu_array.
Retornam (valor, dict_extras).
"""
from __future__ import annotations
import numpy as np
import cv2

from miqa.anatomy.metric_registry import register


def _check(img: np.ndarray) -> np.ndarray:
    assert img.ndim == 2 and img.dtype.kind == "f", "img 2D float esperado"
    return img


# ========== CT BRAIN ==========

@register("ct_brain.sinus_roi_noise")
def ct_brain_sinus_roi_noise(img: np.ndarray, hu_array: np.ndarray = None) -> tuple[float, dict]:
    """Mede ruido em ROI de seios paranasais (ar garantido, nao cantos).
    Resolve problema de ct.air_noise falhar em cranio."""
    arr = hu_array if hu_array is not None else img
    h, w = arr.shape
    # Seios paranasais = regiao inferior central, valores de ar
    # Aproximacao: regiao abaixo dos olhos (inferior 1/3, central)
    sinus_region = arr[2*h//3:, w//3:2*w//3]
    air = sinus_region[sinus_region < -500]
    if len(air) < 50:
        return float("nan"), {"reason": "insufficient air in sinuses"}
    sigma = float(air.std())
    return sigma, {
        "sinus_noise_hu": sigma,
        "n_air_pixels": len(air),
        "sinus_mean_hu": float(air.mean()),
    }


@register("ct_brain.window_bimodal_check")
def ct_brain_window_bimodal_check(img: np.ndarray, hu_array: np.ndarray = None) -> tuple[float, dict]:
    """Verifica se o histograma e bimodal (osso + tecido = janela correta).
    Score alto = bimodal claro (boa janela). Score baixo = unimodal (janela ruim)."""
    arr = hu_array if hu_array is not None else img
    # Histograma
    hist, bins = np.histogram(arr, bins=100)
    # Encontra picos
    from scipy.signal import find_peaks
    peaks, props = find_peaks(hist, height=hist.max() * 0.1, distance=10)
    if len(peaks) >= 2:
        score = 1.0
    elif len(peaks) == 1:
        score = 0.3
    else:
        score = 0.0
    return float(score), {
        "n_peaks": len(peaks),
        "peak_heights": props.get("peak_heights", []).tolist() if len(peaks) > 0 else [],
    }


# ========== CT CHEST ==========

@register("ct_chest.lung_volume_variance")
def ct_chest_lung_volume_variance(img: np.ndarray, hu_array: np.ndarray = None) -> tuple[float, dict]:
    """Variacao de volume pulmonar entre slices (comparar area de ar).
    Esta metrica e para ser usada em volumes — aqui mede area de ar no slice."""
    arr = hu_array if hu_array is not None else img
    # Pulmao = ar (HU < -500)
    lung = arr < -500
    lung_frac = float(lung.mean())
    # Flag se fora do normal
    if 0.15 < lung_frac < 0.55:
        status = "normal"
    elif lung_frac < 0.10:
        status = "atelectasis/consolidation"
    elif lung_frac > 0.65:
        status = "emphysema/hyperinflation"
    else:
        status = "borderline"
    return lung_frac, {
        "lung_area_pct": lung_frac * 100,
        "status": status,
    }


@register("ct_chest.respiratory_motion_index")
def ct_chest_respiratory_motion_index(img: np.ndarray, hu_array: np.ndarray = None,
                                      prev_slice: np.ndarray = None) -> tuple[float, dict]:
    """Indice de motion respiratorio: correlacao com slice anterior na regiao diafragmatica.
    Requer prev_slice. Sem prev_slice retorna NaN."""
    if prev_slice is None:
        return float("nan"), {"reason": "prev_slice required"}
    arr = hu_array if hu_array is not None else img
    h, w = arr.shape
    # Regiao diafragmatica (inferior)
    curr = arr[2*h//3:, :].ravel().astype(np.float32)
    prev = prev_slice[2*h//3:, :].ravel().astype(np.float32)
    if len(curr) != len(prev):
        return float("nan"), {"reason": "shape mismatch"}
    curr -= curr.mean()
    prev -= prev.mean()
    denom = (curr.std() * prev.std()) + 1e-9
    corr = float((curr * prev).mean() / denom)
    # Corr baixa = motion
    motion_score = max(0, 1 - corr)
    return motion_score, {
        "inter_slice_corr": corr,
        "motion_score": motion_score,
    }


# ========== CT ABDOMEN ==========

@register("ct_abdomen.liver_spleen_ratio")
def ct_abdomen_liver_spleen_ratio(img: np.ndarray, hu_array: np.ndarray = None) -> tuple[float, dict]:
    """Relacao de HU entre figado e baco (devem ser similares).
    Diferenca grande = patologia ou artefato."""
    arr = hu_array if hu_array is not None else img
    h, w = arr.shape
    # Heuristica: figado = lado direito (esquerdo da imagem), baco = lado esquerdo
    # Regioes aproximadas (superior abdome)
    liver_region = arr[h//4:h//2, :w//2]
    spleen_region = arr[h//4:h//2, w//2:]
    # Figado: maior componente com HU 40-70
    liver_mask = (liver_region > 30) & (liver_region < 80)
    spleen_mask = (spleen_region > 30) & (spleen_region < 80)
    if liver_mask.sum() < 50 or spleen_mask.sum() < 50:
        return float("nan"), {"reason": "organs not detected"}
    mu_liver = float(liver_region[liver_mask].mean())
    mu_spleen = float(spleen_region[spleen_mask].mean())
    diff = abs(mu_liver - mu_spleen)
    ratio = min(mu_liver, mu_spleen) / max(mu_liver, mu_spleen, 1e-6)
    return float(ratio), {
        "liver_hu": mu_liver,
        "spleen_hu": mu_spleen,
        "diff_hu": diff,
        "ratio": float(ratio),
    }


@register("ct_abdomen.metal_streak_detector")
def ct_abdomen_metal_streak_detector(img: np.ndarray, hu_array: np.ndarray = None) -> tuple[float, dict]:
    """Detecta artefato de streaking por metal.
    Procura linhas radiadas a partir de regioes hiperdensas (>3000 HU)."""
    arr = hu_array if hu_array is not None else img
    h, w = arr.shape
    # Metal = pixels > 3000 HU
    metal = arr > 3000
    if not metal.any():
        return 0.0, {"reason": "no metal detected", "streak_score": 0.0}
    # Detecta linhas usando Hough
    # Binariza para deteccao de linhas
    binary = np.zeros_like(arr, dtype=np.uint8)
    # Streaks = regioes com valores anomalos (muito escuros ou muito claros)
    streaks = (arr < -200) | (arr > 2000)
    binary[streaks] = 255
    # Hough
    lines = cv2.HoughLinesP(binary, 1, np.pi/180, threshold=50,
                            minLineLength=max(h, w)//4, maxLineGap=10)
    if lines is None:
        return 0.0, {"streak_score": 0.0, "n_lines": 0}
    # Filtra linhas que passam perto do metal
    metal_y, metal_x = np.where(metal)
    metal_center = (int(metal_x.mean()), int(metal_y.mean()))
    streak_lines = 0
    for line in lines:
        x1, y1, x2, y2 = line[0]
        # Distancia do centro do metal
        d = abs((y2-y1)*metal_center[0] - (x2-x1)*metal_center[1] + x2*y1 - y2*x1)
        d = d / np.sqrt((y2-y1)**2 + (x2-x1)**2 + 1e-9)
        if d < 50:
            streak_lines += 1
    score = min(1.0, streak_lines / 5)
    return float(score), {
        "streak_score": float(score),
        "n_streak_lines": streak_lines,
        "metal_detected": True,
    }


# ========== CT SPINE ==========

@register("ct_spine.vertebral_alignment")
def ct_spine_vertebral_alignment(img: np.ndarray, hu_array: np.ndarray = None) -> tuple[float, dict]:
    """Alinhamento vertebral: detecta escoliose ou rotacao.
    Mede desvio da coluna vertebral da vertical."""
    arr = hu_array if hu_array is not None else img
    h, w = arr.shape
    # Vertebra = osso central (HU > 200)
    bone = (arr > 200).astype(np.uint8)
    # Componentes
    n, labels, stats, _ = cv2.connectedComponentsWithStats(bone)
    if n <= 1:
        return float("nan"), {"reason": "no bone detected"}
    # Pega componentes centrais (vertebras)
    centroids = []
    for k in range(1, n):
        y = stats[k, cv2.CC_STAT_TOP] + stats[k, cv2.CC_STAT_HEIGHT] // 2
        x = stats[k, cv2.CC_STAT_LEFT] + stats[k, cv2.CC_STAT_WIDTH] // 2
        # So componentes centrais
        if w // 4 < x < 3 * w // 4:
            centroids.append((y, x, stats[k, cv2.CC_STAT_AREA]))
    if len(centroids) < 3:
        return float("nan"), {"reason": "insufficient vertebrae"}
    # Ajusta linha
    centroids = sorted(centroids, key=lambda t: t[0])  # ordena por Y
    ys = np.array([c[0] for c in centroids])
    xs = np.array([c[1] for c in centroids])
    # Regressao linear
    slope, intercept = np.polyfit(ys, xs, 1)
    angle = abs(np.degrees(np.arctan(slope)))
    # Angulo < 5 graus = alinhado
    score = max(0, 1 - angle / 15)
    return float(score), {
        "alignment_angle_deg": float(angle),
        "n_vertebrae": len(centroids),
        "score": float(score),
    }
