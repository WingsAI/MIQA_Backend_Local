"""Degradações sintéticas controladas para validar métricas.

Premissa: se uma métrica claim ser de nitidez, ela DEVE cair quando aplicamos
blur. Se claim ser de contraste, deve cair quando comprimimos a faixa.
Sem isso, a métrica é teatro.
"""
from __future__ import annotations
import numpy as np
import cv2


def make_phantom(shape=(256, 256), seed: int = 42) -> np.ndarray:
    """Phantom sintético com bordas, gradiente e textura — substituto de imagem real."""
    rng = np.random.default_rng(seed)
    h, w = shape
    img = np.zeros(shape, dtype=np.float32)
    # gradiente vertical
    img += np.linspace(0.2, 0.8, h)[:, None]
    # disco branco central
    yy, xx = np.mgrid[:h, :w]
    cy, cx = h // 2, w // 2
    img[(yy - cy) ** 2 + (xx - cx) ** 2 < (h // 6) ** 2] = 0.95
    # textura suave
    img += 0.05 * rng.standard_normal(shape).astype(np.float32)
    return np.clip(img, 0, 1)


def add_gaussian_blur(img: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return img.copy()
    k = max(3, int(2 * round(3 * sigma) + 1))
    return cv2.GaussianBlur(img, (k, k), sigma).astype(np.float32)


def add_gaussian_noise(img: np.ndarray, std: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = img + rng.standard_normal(img.shape).astype(np.float32) * std
    return np.clip(out, 0, 1)


def reduce_contrast(img: np.ndarray, factor: float) -> np.ndarray:
    """factor=1.0 mantém, factor=0.0 vira cinza médio."""
    m = img.mean()
    return np.clip(m + (img - m) * factor, 0, 1).astype(np.float32)


def clip_intensity(img: np.ndarray, low: float = 0.0, high: float = 1.0) -> np.ndarray:
    """Força saturação: tudo abaixo de `low` vira 0, acima de `high` vira 1."""
    out = img.copy()
    out[out < low] = 0
    out[out > high] = 1
    return out
