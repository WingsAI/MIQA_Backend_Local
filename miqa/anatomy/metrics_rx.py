"""Métricas RX anatomy-aware — por exame/anatomia.

Todas as funções recebem img: np.ndarray 2D float [0,1] e retornam (valor, dict_extras).
"""
from __future__ import annotations
import numpy as np
import cv2

from miqa.anatomy.metric_registry import register


def _check(img: np.ndarray) -> np.ndarray:
    assert img.ndim == 2 and img.dtype.kind == "f", "img 2D float esperado"
    return img


# ========== RX CHEST ==========

@register("rx_chest.lung_symmetry")
def rx_chest_lung_symmetry(img: np.ndarray) -> tuple[float, dict]:
    """Compara histograma hemitorax esquerdo vs direito.
    Valor próximo de 1.0 = simétrico (bom). Próximo de 0 = assimetria forte."""
    img = _check(img)
    h, w = img.shape
    left = img[:, :w//2]
    right = img[:, w//2:]
    # Correlacao de Pearson dos histogramas
    hist_l, _ = np.histogram(left, bins=50, range=(0, 1))
    hist_r, _ = np.histogram(right, bins=50, range=(0, 1))
    hist_l = hist_l.astype(float) / max(hist_l.sum(), 1)
    hist_r = hist_r.astype(float) / max(hist_r.sum(), 1)
    # Correlation
    mean_l, mean_r = hist_l.mean(), hist_r.mean()
    num = ((hist_l - mean_l) * (hist_r - mean_r)).sum()
    den = np.sqrt(((hist_l - mean_l)**2).sum() * ((hist_r - mean_r)**2).sum())
    corr = float(num / max(den, 1e-9))
    # Map to [0,1]: corr of -1 -> 0, corr of 1 -> 1
    score = (corr + 1) / 2
    return score, {
        "correlation": corr,
        "left_mean": float(left.mean()),
        "right_mean": float(right.mean()),
    }


@register("rx_chest.inspiration_index")
def rx_chest_inspiration_index(img: np.ndarray) -> tuple[float, dict]:
    """Indice de inspiracao: area pulmonar (escura) / area total do torax.
    Valor tipico: 0.35-0.55. <0.25 = expiracao/hipoinspiracao. >0.65 = hiperinsuflacao."""
    img = _check(img)
    h, w = img.shape
    # Detectar torax (regiao central, exclui bordas)
    margin_y, margin_x = h // 8, w // 8
    chest = img[margin_y:-margin_y, margin_x:-margin_x]
    # Pulmao = pixels escuros (ar)
    thr = np.percentile(chest, 40)  # parte mais escura
    lung_mask = chest <= thr
    lung_area = float(lung_mask.mean())
    return lung_area, {
        "lung_area_pct": lung_area * 100,
        "threshold": float(thr),
    }


@register("rx_chest.mediastinum_width")
def rx_chest_mediastinum_width(img: np.ndarray) -> tuple[float, dict]:
    """Largura relativa do mediastino (regiao central clara) vs largura total.
    Valor tipico: 0.25-0.40. >0.50 pode indicar cardiomegalia ou massa."""
    img = _check(img)
    h, w = img.shape
    # Regiao central vertical
    central = img[h//4:3*h//4, :]
    # Media por coluna
    col_mean = central.mean(axis=0)
    # Mediastino = colunas claras (acima da mediana)
    med = float(np.median(col_mean))
    mediastinum_mask = col_mean > med
    # Encontra maior bloco continuo
    if not mediastinum_mask.any():
        return float("nan"), {"reason": "no mediastinum detected"}
    # Largura do bloco central
    center_idx = w // 2
    left_edge = center_idx
    right_edge = center_idx
    for i in range(center_idx, -1, -1):
        if mediastinum_mask[i]:
            left_edge = i
        else:
            break
    for i in range(center_idx, w):
        if mediastinum_mask[i]:
            right_edge = i
        else:
            break
    width = (right_edge - left_edge) / w
    return float(width), {
        "width_px": int(right_edge - left_edge),
        "width_relative": float(width),
    }


@register("rx_chest.rotation_angle")
def rx_chest_rotation_angle(img: np.ndarray) -> tuple[float, dict]:
    """Estima rotacao do paciente comparando distancia clavicula-centro.
    Retorna angulo estimado em graus (0 = centrado)."""
    img = _check(img)
    h, w = img.shape
    # Regiao superior (claviculas)
    top = img[:h//3, :]
    # Encontra bordas superiores
    edges = cv2.Canny((top * 255).astype(np.uint8), 50, 150)
    # Pontos de borda
    ys, xs = np.where(edges > 0)
    if len(xs) < 10:
        return float("nan"), {"reason": "insufficient edges"}
    # Ajusta linha
    coords = np.column_stack([xs, ys])
    [vx, vy, x0, y0] = cv2.fitLine(coords, cv2.DIST_L2, 0, 0.01, 0.01)
    angle = float(np.degrees(np.arctan2(vy, vx)))
    # Normaliza para [-45, 45]
    angle = ((angle + 90) % 180) - 90
    return abs(angle), {
        "angle_deg": abs(angle),
        "n_edge_points": len(xs),
    }


# ========== RX EXTREMITY ==========

@register("rx_extremity.bone_snr")
def rx_extremity_bone_snr(img: np.ndarray) -> tuple[float, dict]:
    """SNR em regiao ossea vs fundo. ROI em osso cortical (claro)."""
    img = _check(img)
    h, w = img.shape
    # Ossos = pixels claros
    thr = np.percentile(img, 85)
    bone_mask = img > thr
    if bone_mask.sum() < 100:
        return float("nan"), {"reason": "no bone detected"}
    bone_mu = float(img[bone_mask].mean())
    # Fundo = pixels escuros
    bg_mask = img <= np.percentile(img, 15)
    if bg_mask.sum() < 100:
        return float("nan"), {"reason": "no background detected"}
    bg_sigma = float(img[bg_mask].std())
    if bg_sigma < 1e-6:
        return float("nan"), {"reason": "background uniform"}
    snr = bone_mu / bg_sigma
    return float(snr), {
        "bone_mu": bone_mu,
        "bg_sigma": bg_sigma,
        "bone_area_pct": float(bone_mask.mean() * 100),
    }


@register("rx_extremity.alignment_score")
def rx_extremity_alignment_score(img: np.ndarray) -> tuple[float, dict]:
    """Verifica alinhamento do membro (eixo principal deve ser vertical/horizontal).
    Retorna score [0,1]: 1.0 = alinhado, 0.0 = rotacao grande."""
    img = _check(img)
    h, w = img.shape
    # Binarizacao para encontrar osso
    _, binary = cv2.threshold((img * 255).astype(np.uint8), 0, 255,
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Componentes conectados
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
    if n <= 1:
        return float("nan"), {"reason": "no components"}
    # Maior componente
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    mask = (labels == largest).astype(np.uint8)
    # Momentos
    moments = cv2.moments(mask)
    if moments['mu02'] == 0:
        return 1.0, {"reason": "perfect vertical"}
    # Angulo do eixo principal
    angle = 0.5 * np.arctan2(2 * moments['mu11'],
                              moments['mu20'] - moments['mu02'])
    angle_deg = abs(np.degrees(angle))
    # Score: 0-15 graus = bom, >45 = ruim
    score = max(0, 1 - angle_deg / 45)
    return float(score), {
        "angle_deg": float(angle_deg),
        "area": int(stats[largest, cv2.CC_STAT_AREA]),
    }


@register("rx_extremity.bone_penetration")
def rx_extremity_bone_penetration(img: np.ndarray) -> tuple[float, dict]:
    """Indice de penetracao ossea: contraste entre cortical e medular.
    Valor alto = boa penetracao (ve detalhes). Baixo = subpenetrado ou superpenetrado."""
    img = _check(img)
    # Ossos = pixels claros
    p80 = np.percentile(img, 80)
    p95 = np.percentile(img, 95)
    cortical = (img >= p80) & (img <= p95)
    medullary = (img >= p60) if (p60 := np.percentile(img, 60)) else False
    # Ajuste
    p60 = np.percentile(img, 60)
    medullary = (img >= p60) & (img < p80)
    if cortical.sum() < 50 or medullary.sum() < 50:
        return float("nan"), {"reason": "insufficient bone regions"}
    mu_cort = float(img[cortical].mean())
    mu_med = float(img[medullary].mean())
    contrast = abs(mu_cort - mu_med)
    return float(contrast), {
        "cortical_mu": mu_cort,
        "medullary_mu": mu_med,
        "contrast": float(contrast),
    }


# ========== RX SKULL ==========

@register("rx_skull.penetration_index")
def rx_skull_penetration_index(img: np.ndarray) -> tuple[float, dict]:
    """Indice de penetracao em cranio: contraste frontal vs temporal.
    Valor adequado quando ambas as regioes sao visiveis."""
    img = _check(img)
    h, w = img.shape
    # Regioes aproximadas
    frontal = img[h//4:h//2, w//3:2*w//3]
    temporal_l = img[h//3:2*h//3, :w//4]
    temporal_r = img[h//3:2*h//3, 3*w//4:]
    temporal = np.concatenate([temporal_l, temporal_r])
    if frontal.size == 0 or temporal.size == 0:
        return float("nan"), {"reason": "invalid regions"}
    mu_frontal = float(frontal.mean())
    mu_temporal = float(temporal.mean())
    ratio = min(mu_frontal, mu_temporal) / max(mu_frontal, mu_temporal, 1e-6)
    return float(ratio), {
        "frontal_mu": mu_frontal,
        "temporal_mu": mu_temporal,
        "balance": float(ratio),
    }


@register("rx_skull.sinus_air_score")
def rx_skull_sinus_air_score(img: np.ndarray) -> tuple[float, dict]:
    """Detecta presenca de ar nos seios (regiao escura abaixo da fronte).
    Escuridao esperada = ar nos seios paranasais."""
    img = _check(img)
    h, w = img.shape
    # Regiao dos seios (abaixo da fronte, acima do nariz)
    sinus_region = img[h//5:h//3, w//3:2*w//3]
    dark_frac = float((sinus_region < 0.3).mean())
    # Score: 0.15-0.45 = normal, fora = patologico ou tecnico
    if 0.10 < dark_frac < 0.50:
        score = 1.0 - abs(dark_frac - 0.30) / 0.30
    else:
        score = 0.0
    return float(score), {
        "dark_fraction": dark_frac,
        "sinus_area_pct": dark_frac * 100,
    }


# ========== RX ABDOMEN ==========

@register("rx_abdomen.nps_fat")
def rx_abdomen_nps_fat(img: np.ndarray) -> tuple[float, dict]:
    """NPS em regiao de gordura subcutanea (textura caracteristica).
    Mede granularidade da gordura — alteracao pode indicar tecnica ruim."""
    img = _check(img)
    h, w = img.shape
    # Gordura subcutanea = regiao superior lateral, intensidade media
    region = img[:h//3, :]
    m, s = float(region.mean()), float(region.std())
    if s < 0.01:
        return float("nan"), {"reason": "uniform region"}
    # FFT da regiao
    f = np.fft.fft2(region - m)
    ps = np.abs(f) ** 2
    ps = np.fft.fftshift(ps)
    # Energia em alta frequencia
    cy, cx = region.shape[0] // 2, region.shape[1] // 2
    yy, xx = np.mgrid[:region.shape[0], :region.shape[1]]
    r = np.sqrt((yy - cy)**2 + (xx - cx)**2)
    r_max = min(cy, cx)
    high = ps[(r >= 0.5 * r_max) & (r < r_max)].sum()
    total = ps.sum()
    ratio = float(high / max(total, 1e-9))
    return ratio, {
        "high_freq_ratio": ratio,
        "region_std": s,
    }


@register("rx_abdomen.free_air_detector")
def rx_abdomen_free_air_detector(img: np.ndarray) -> tuple[float, dict]:
    """Detecta ar livre sob o diafragma (regiao escura abaixo das costelas).
        Flag tecnica/posicao: paciente deitado de lado deve mostrar ar no topo."""
    img = _check(img)
    h, w = img.shape
    # Regiao subdiafragmatica (topo da imagem em decubito)
    subdiaphragm = img[:h//4, :]
    dark_frac = float((subdiaphragm < 0.2).mean())
    # Em RX abdomen de pe: ar livre = patologico (score baixo)
    # Em RX abdomen deitado: ar no topo = normal (score alto)
    # Heuristica: muito escuro no topo = possivel ar livre
    score = dark_frac  # Usar como flag, nao score absoluto
    return float(score), {
        "subdiaphragm_dark_pct": dark_frac * 100,
        "flag": "possible_free_air" if dark_frac > 0.3 else "normal",
    }
