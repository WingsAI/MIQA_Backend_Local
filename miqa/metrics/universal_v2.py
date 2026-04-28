"""Métricas universais v2 — NR-IQA clássicos via pyiqa.

NIQE  (Mittal et al. 2013): natural-image statistics. Quanto MENOR, melhor.
BRISQUE (Mittal et al. 2012): regressor treinado em distorções. MENOR = melhor.

Ambos esperam imagem [0,1] float, formato torch tensor [B, C, H, W]. Convertemos
grayscale → 3 canais replicando (que é o que pyiqa internamente faz pra essas).
Modelos são singletons cacheados — primeiro uso baixa pesos.
"""
from __future__ import annotations
import functools
import warnings
import numpy as np
import torch
import pyiqa


# NIQE usa float64 internamente, que MPS não suporta. CPU para NIQE; MPS pode pra BRISQUE.
_FORCE_CPU = {"niqe"}

@functools.lru_cache(maxsize=4)
def _get_metric(name: str):
    if name in _FORCE_CPU:
        device = "cpu"
    else:
        device = "mps" if torch.backends.mps.is_available() else "cpu"
    try:
        m = pyiqa.create_metric(name, device=device)
    except Exception:
        m = pyiqa.create_metric(name, device="cpu")
    m.eval()
    return m


def _to_tensor(img: np.ndarray) -> torch.Tensor:
    assert img.ndim == 2 and img.dtype.kind == "f", "img 2D float esperado"
    img = np.clip(img, 0, 1)
    rgb = np.stack([img, img, img], axis=0)        # 3xHxW
    return torch.from_numpy(rgb).unsqueeze(0).float()  # 1x3xHxW


def _safe_eval(metric_name: str, img: np.ndarray) -> tuple[float, dict]:
    try:
        m = _get_metric(metric_name)
        x = _to_tensor(img).to(next(m.parameters()).device if list(m.parameters()) else "cpu")
        with torch.no_grad(), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            v = m(x).item()
        return float(v), {}
    except Exception as e:
        return float("nan"), {"error": str(e)[:120]}


def niqe(img: np.ndarray) -> tuple[float, dict]:
    """NIQE — quanto MENOR, melhor (típico 2-15 em imagens naturais)."""
    return _safe_eval("niqe", img)


def brisque(img: np.ndarray) -> tuple[float, dict]:
    """BRISQUE — quanto MENOR, melhor (escala 0-100; <30 bom, >50 ruim)."""
    return _safe_eval("brisque", img)


ALL_V2 = {"niqe": niqe, "brisque": brisque}


def run_all_v2(img: np.ndarray) -> dict:
    out = {}
    for name, fn in ALL_V2.items():
        v, extra = fn(img)
        out[name] = {"value": v, **extra}
    return out
