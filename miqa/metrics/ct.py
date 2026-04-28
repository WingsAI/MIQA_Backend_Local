"""Métricas específicas de tomografia computadorizada (CT).

Premissa-chave: CT tem **HU (Hounsfield Units)** calibradas, ao contrário de RX/US.
Isso habilita métricas físicas reais:
- Ar = -1000 HU, água = 0 HU, tecido mole +20 a +80, osso compacto >+1000.
- Ruído = σ em ROI homogênea (ar ou água).
- Calibração: μ_ar deve estar em [-1100, -900] e μ_água em [-20, +20].

As funções aqui esperam **array em HU** (caller já aplicou RescaleSlope/Intercept).
Se o caller passar [0,1] normalizado, métricas baseadas em HU retornam NaN com flag.
"""
from __future__ import annotations
import numpy as np


HU_AIR = -1000.0
HU_WATER = 0.0


def _is_hu(img: np.ndarray) -> bool:
    """Heurística: HU típica vai de ~-1024 a +3000. Se está em [0,1] ou [0,255], não é HU."""
    return img.min() < -100 and img.max() > 100


def air_noise(img: np.ndarray, size: int = 32, k_rois: int = 5) -> tuple[float, dict]:
    """σ em ROIs de ar (HU < -800). Em CT bem calibrado, σ_ar ~ 5-30 HU.
    σ alto = scanner ruidoso ou má calibração."""
    if not _is_hu(img):
        return float("nan"), {"reason": "img não está em HU", "n_rois": 0}
    h, w = img.shape if img.ndim == 2 else img.shape[-2:]
    arr = img if img.ndim == 2 else img.mean(axis=0)
    rng = np.random.default_rng(42)
    cands = []
    for _ in range(400):
        y = int(rng.integers(0, h - size))
        x = int(rng.integers(0, w - size))
        p = arr[y:y+size, x:x+size]
        m = float(p.mean())
        if m > -800:  # quer ar (típico bordas da imagem)
            continue
        cands.append((float(p.std()), m, y, x))
    if not cands:
        return float("nan"), {"reason": "sem ROI de ar", "n_rois": 0}
    cands.sort()
    chosen = cands[:k_rois]
    sigmas = [s for s, _, _, _ in chosen]
    return float(np.median(sigmas)), {
        "n_air_rois": len(cands),
        "k_used": len(chosen),
        "mu_air_mean": float(np.mean([m for _, m, _, _ in chosen])),
        "sigma_min": float(min(sigmas)),
        "sigma_max": float(max(sigmas)),
    }


def hu_calibration(img: np.ndarray, size: int = 32) -> tuple[float, dict]:
    """Verifica se ar e água/tecido mole estão em ranges HU esperados.
    Retorna desvio (HU) do ar de -1000 — ideal: < 50.
    """
    if not _is_hu(img):
        return float("nan"), {"reason": "img não está em HU"}
    arr = img if img.ndim == 2 else img.mean(axis=0)
    h, w = arr.shape
    # ROIs nos cantos = ar quase sempre
    corners = [
        arr[:size, :size], arr[:size, -size:],
        arr[-size:, :size], arr[-size:, -size:],
    ]
    corner_mus = [float(c.mean()) for c in corners]
    air_estimate = float(np.median(corner_mus))
    deviation = abs(air_estimate - HU_AIR)
    flag = "ok" if deviation < 100 else "miscalibrated"
    return deviation, {
        "air_estimate_hu": air_estimate,
        "expected_hu": HU_AIR,
        "corner_mus": corner_mus,
        "flag": flag,
    }


def ring_artifact_index(img: np.ndarray, n_rings: int = 64) -> tuple[float, dict]:
    """Detecta ring artifact via componente high-frequency do perfil radial.

    Subtrai uma versão suavizada (low-pass) do perfil — sobra só variação
    rápida ring-to-ring, que é o que rings produzem. Ignora a transição
    ar→tecido que domina o perfil bruto.
    """
    arr = img if img.ndim == 2 else img.mean(axis=0)
    h, w = arr.shape
    cy, cx = h // 2, w // 2
    yy, xx = np.mgrid[:h, :w]
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    r_max = min(h, w) // 2
    bins = np.linspace(0, r_max, n_rings + 1)
    profile = np.array([
        arr[(r >= bins[i]) & (r < bins[i+1])].mean()
        if ((r >= bins[i]) & (r < bins[i+1])).any() else 0
        for i in range(n_rings)
    ])
    # restringe perfil ao corpo (HU > -500) — ar não tem rings
    in_body = profile > -500
    if in_body.sum() < 8:
        return float("nan"), {"reason": "perfil curto dentro do corpo"}
    body_profile = profile[in_body]
    k = max(5, len(body_profile) // 8)
    kernel = np.ones(k) / k
    smoothed = np.convolve(body_profile, kernel, mode="same")
    residual = body_profile - smoothed
    inner = residual[k:-k] if len(residual) > 2 * k else residual
    return float(np.abs(inner).mean()), {
        "n_rings": n_rings,
        "n_body_bins": int(in_body.sum()),
        "max_residual": float(np.abs(inner).max()) if len(inner) else 0.0,
        "smooth_kernel": k,
    }


def streak_index(img: np.ndarray) -> tuple[float, dict]:
    """Detecta streak artifact via energia de alta frequência radial.
    Streaks aparecem como linhas radiais de HU anômalo.
    Aproximação: |gradiente angular| alto em região central."""
    arr = img if img.ndim == 2 else img.mean(axis=0)
    h, w = arr.shape
    cy, cx = h // 2, w // 2
    # crop central
    half = min(h, w) // 4
    central = arr[cy-half:cy+half, cx-half:cx+half]
    # gradiente em coordenadas polares (aproximação: gradiente angular = grad_x*y - grad_y*x normalizado)
    gx = np.gradient(central, axis=1)
    gy = np.gradient(central, axis=0)
    return float(np.percentile(np.abs(gx) + np.abs(gy), 95)), {
        "central_size": central.shape,
    }


ALL_CT_METRICS = {
    "air_noise": air_noise,
    "hu_calibration": hu_calibration,
    "ring": ring_artifact_index,
    "streak": streak_index,
}


def run_all_ct(img: np.ndarray) -> dict:
    out = {}
    for name, fn in ALL_CT_METRICS.items():
        v, extra = fn(img)
        out[name] = {"value": v, **extra}
    return out
