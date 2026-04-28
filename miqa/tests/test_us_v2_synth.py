"""Validação sintética US v2."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
import cv2
from miqa.metrics.us_v2 import speckle_anisotropy, lateral_resolution_proxy, tgc_consistency


def make_speckle(shape=(400, 400), seed=42):
    """Speckle isotrópico (ruído gaussiano filtrado por kernel circular)."""
    rng = np.random.default_rng(seed)
    n = rng.standard_normal(shape).astype(np.float32)
    return cv2.GaussianBlur(n, (9, 9), 1.5) * 0.2 + 0.5


def make_anisotropic_speckle(shape=(400, 400), kx=15, ky=3, seed=42):
    """Speckle alongado horizontal (kernel anisotrópico: kx > ky)."""
    rng = np.random.default_rng(seed)
    n = rng.standard_normal(shape).astype(np.float32)
    # kernel separável anisotrópico
    kx = max(3, kx | 1); ky = max(3, ky | 1)
    return cv2.GaussianBlur(n, (kx, ky), 0) * 0.2 + 0.5


def make_us_with_attenuation(shape=(400, 400), decay=0.005, seed=42):
    rng = np.random.default_rng(seed)
    h, w = shape
    profile = 0.7 * np.exp(-decay * np.arange(h))
    img = np.tile(profile[:, None], (1, w)).astype(np.float32)
    img += rng.standard_normal(shape).astype(np.float32) * 0.04
    return np.clip(img, 0, 1)


def make_us_tgc_ok(shape=(400, 400), seed=42):
    rng = np.random.default_rng(seed)
    return np.clip(0.5 + rng.standard_normal(shape).astype(np.float32) * 0.04, 0, 1)


def check(name, cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}: {msg}")
    return cond


def main():
    n_pass = n_fail = 0

    print("=== speckle_anisotropy: ratio ~1 isotrópico, >>1 anisotrópico ===")
    iso = speckle_anisotropy(make_speckle())[0]
    aniso = speckle_anisotropy(make_anisotropic_speckle(kx=15, ky=3))[0]
    ok = aniso > 2.0 and iso < 1.5
    if check("speckle_anisotropy", ok, f"iso={iso:.2f} aniso={aniso:.2f}"): n_pass += 1
    else: n_fail += 1

    print("\n=== lateral_resolution_px: SOBE com kernel mais largo (PSF mais ampla) ===")
    fine = lateral_resolution_proxy(make_speckle(seed=1))[0]
    coarse_img = cv2.GaussianBlur(make_speckle(seed=1), (15, 15), 5)
    coarse = lateral_resolution_proxy(coarse_img)[0]
    ok = coarse > fine * 1.5
    if check("lateral_resolution_px", ok, f"fine={fine:.0f} coarse={coarse:.0f}"): n_pass += 1
    else: n_fail += 1

    print("\n=== tgc_cov: BAIXO em phantom uniforme, ALTO sob atenuação ===")
    cov_ok = tgc_consistency(make_us_tgc_ok())[0]
    cov_bad = tgc_consistency(make_us_with_attenuation(decay=0.01))[0]
    ok = cov_bad > 3 * cov_ok
    if check("tgc_cov", ok, f"ok={cov_ok:.3f} bad={cov_bad:.3f}"): n_pass += 1
    else: n_fail += 1

    print(f"\n=== {n_pass} passed, {n_fail} failed ===")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
