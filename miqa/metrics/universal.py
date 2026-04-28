"""Métricas universais NR-IQA aplicáveis a qualquer modalidade.

Convenção de entrada: numpy array 2D float em [0,1] (grayscale). Funções de
conversão (DICOM→array, RGB→gray) ficam em pipelines/, não aqui.

Cada função retorna (valor, dict_extra). O caller decide flag/threshold por
modalidade — um valor "bom" pra RX pode ser ruim pra US.
"""
from __future__ import annotations
import numpy as np
import cv2


def _check(img: np.ndarray) -> np.ndarray:
    assert img.ndim == 2, f"esperado 2D, recebi {img.shape}"
    assert img.dtype.kind == "f", f"esperado float, recebi {img.dtype}"
    if img.min() < 0 or img.max() > 1:
        # tolera [0,255] ou [0,4095] e normaliza
        img = (img - img.min()) / (img.max() - img.min() + 1e-9)
    return img


def laplacian_var(img: np.ndarray) -> tuple[float, dict]:
    """Variância do Laplaciano = nitidez. Maior = mais nítido.
    Borrado idealmente cai abaixo de ~50% do baseline."""
    img = _check(img)
    lap = cv2.Laplacian((img * 255).astype(np.uint8), cv2.CV_64F)
    return float(lap.var()), {"unit": "var(Lap[0..255])"}


def laplacian_snr(img: np.ndarray) -> tuple[float, dict]:
    """Razão estrutura/ruído robusta: percentil 95 de |Lap| / MAD de |Lap|.

    - p95 de |Lap| reflete picos de gradiente (bordas reais — *estrutura*).
    - MAD de |Lap| é dominado pelo "fundo" de Laplaciano (ruído).
    - Razão alta = estrutura nítida sobre fundo pouco ruidoso.
    - Robusta a fator multiplicativo no ruído (denominador escala junto).
    """
    img = _check(img)
    lap = cv2.Laplacian((img * 255).astype(np.uint8), cv2.CV_64F)
    a = np.abs(lap)
    p95 = float(np.percentile(a, 95))
    med = float(np.median(a))
    mad = float(np.median(np.abs(a - med)))
    denom = max(mad * 1.4826, 1e-6)  # 1.4826: MAD → σ-equivalente
    return p95 / denom, {"p95_abs_lap": p95, "mad_abs_lap": mad}


def shannon_entropy(img: np.ndarray, bins: int = 256) -> tuple[float, dict]:
    """Entropia de Shannon do histograma. Mais alta = mais informação/contraste.
    Imagem uniforme → ~0; ruído branco → log2(bins)."""
    img = _check(img)
    hist, _ = np.histogram(img, bins=bins, range=(0, 1), density=False)
    p = hist / hist.sum()
    p = p[p > 0]
    H = float(-(p * np.log2(p)).sum())
    return H, {"max_possible": float(np.log2(bins))}


def rms_contrast(img: np.ndarray) -> tuple[float, dict]:
    """RMS contrast = desvio padrão da intensidade normalizada [0,1]."""
    img = _check(img)
    return float(img.std()), {}


def clipping_pct(img: np.ndarray, low: float = 0.01, high: float = 0.99) -> tuple[float, dict]:
    """% de pixels saturados (preto puro ou branco puro). Alto = sub/superexposto."""
    img = _check(img)
    n = img.size
    p_low = float((img <= low).sum() / n * 100)
    p_high = float((img >= high).sum() / n * 100)
    return p_low + p_high, {"low_pct": p_low, "high_pct": p_high}


def dynamic_range_usage(img: np.ndarray, p_lo: float = 1, p_hi: float = 99) -> tuple[float, dict]:
    """Faixa entre percentis 1-99 normalizada. 1.0 = usa toda a faixa, baixo = comprimida."""
    img = _check(img)
    lo, hi = np.percentile(img, [p_lo, p_hi])
    return float(hi - lo), {"p_lo": float(lo), "p_hi": float(hi)}


def tenengrad(img: np.ndarray) -> tuple[float, dict]:
    """Sharpness via gradiente Sobel (alternativa robusta ao Laplaciano)."""
    img = _check(img)
    g = (img * 255).astype(np.uint8)
    gx = cv2.Sobel(g, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_64F, 0, 1, ksize=3)
    return float(np.mean(gx ** 2 + gy ** 2)), {}


ALL_METRICS = {
    "laplacian_var": laplacian_var,
    "laplacian_snr": laplacian_snr,
    "tenengrad": tenengrad,
    "entropy": shannon_entropy,
    "rms_contrast": rms_contrast,
    "clipping_pct": clipping_pct,
    "dynamic_range": dynamic_range_usage,
}


def run_all(img: np.ndarray) -> dict:
    """Roda todas as métricas universais e devolve dict {nome: {value, extra}}."""
    out = {}
    for name, fn in ALL_METRICS.items():
        v, extra = fn(img)
        out[name] = {"value": v, **extra}
    return out
