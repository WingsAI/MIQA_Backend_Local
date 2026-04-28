"""Catálogo de degradações controladas — para grid dose-resposta.

Cada função recebe img float32 [0,1] 2D e parâmetro k, retorna img degradada.
"""
from __future__ import annotations
import numpy as np
import cv2

from miqa.synthetic.degradations import (
    add_gaussian_blur, add_gaussian_noise,
    reduce_contrast, clip_intensity,
)


def degrade_jpeg(img: np.ndarray, quality: int) -> np.ndarray:
    """Re-encode JPEG com qualidade Q. Tipica Q=90 boa, Q=10 horrível."""
    src = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    ok, enc = cv2.imencode(".jpg", src, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        return img.copy()
    dec = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
    return (dec.astype(np.float32) / 255).astype(np.float32)


def degrade_quantize(img: np.ndarray, bits: int) -> np.ndarray:
    """Quantização para B bits (4=16 níveis, 8=256, etc)."""
    levels = 2 ** int(bits)
    q = np.round(img * (levels - 1)) / (levels - 1)
    return q.astype(np.float32)


def degrade_downup(img: np.ndarray, scale: float) -> np.ndarray:
    """Reduz e re-amplia (perda de resolução proporcional a scale)."""
    h, w = img.shape
    h2, w2 = max(8, int(h * scale)), max(8, int(w * scale))
    small = cv2.resize(img, (w2, h2), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32)


# Catálogo: nome → (função, lista de níveis k, label do parâmetro)
DEGRADATIONS = {
    "noise":        (add_gaussian_noise, [0.01, 0.02, 0.05, 0.10, 0.15], "σ"),
    "blur":         (add_gaussian_blur,  [0.5, 1.0, 2.0, 3.0, 5.0],     "σ_px"),
    "contrast":     (reduce_contrast,    [0.8, 0.6, 0.4, 0.2, 0.05],    "factor"),
    "jpeg":         (degrade_jpeg,       [90, 70, 50, 30, 10],          "quality"),
    "quantize":     (degrade_quantize,   [12, 8, 6, 4, 3],              "bits"),
    "downup":       (degrade_downup,     [0.7, 0.5, 0.3, 0.2, 0.1],     "scale"),
}
