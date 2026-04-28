"""Validação das métricas CT em phantoms HU sintéticos."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
from miqa.metrics.ct import air_noise, hu_calibration, ring_artifact_index, streak_index


def make_ct_phantom(shape=(512, 512), bg_hu=-1000, body_hu=40, body_radius=180,
                    sigma_air=10, sigma_body=15, seed=42):
    """Phantom CT: ar de fundo + disco de tecido mole + ruído realista em cada região."""
    rng = np.random.default_rng(seed)
    h, w = shape
    yy, xx = np.mgrid[:h, :w]
    cy, cx = h // 2, w // 2
    body_mask = (yy - cy) ** 2 + (xx - cx) ** 2 < body_radius ** 2
    img = np.full(shape, bg_hu, dtype=np.float32)
    img[body_mask] = body_hu
    noise = rng.standard_normal(shape).astype(np.float32)
    img[~body_mask] += noise[~body_mask] * sigma_air
    img[body_mask]  += noise[body_mask]  * sigma_body
    return img


def add_rings(img, n_rings=4, amp=30):
    h, w = img.shape
    yy, xx = np.mgrid[:h, :w]
    r = np.sqrt((yy - h//2)**2 + (xx - w//2)**2)
    r_max = min(h, w) // 2
    for k in range(n_rings):
        rad = r_max * (k + 1) / (n_rings + 1)
        ring = (np.abs(r - rad) < 2).astype(np.float32) * amp
        img = img + ring
    return img


def check(name, cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}: {msg}")
    return cond


def main():
    n_pass = n_fail = 0

    print("=== air_noise (deve SUBIR com mais ruído no ar) ===")
    n_low = air_noise(make_ct_phantom(sigma_air=5))[0]
    n_high = air_noise(make_ct_phantom(sigma_air=30))[0]
    ok = n_high > 2 * n_low
    if check("air_noise", ok, f"σ=5 → ruído={n_low:.1f} HU | σ=30 → ruído={n_high:.1f} HU"): n_pass += 1
    else: n_fail += 1

    print("\n=== hu_calibration (deve flagar miscal) ===")
    img_ok = make_ct_phantom(bg_hu=-1000)
    img_bad = make_ct_phantom(bg_hu=-700)  # ar errado em -700 HU
    f_ok = hu_calibration(img_ok)[1]["flag"]
    f_bad = hu_calibration(img_bad)[1]["flag"]
    ok = f_ok == "ok" and f_bad == "miscalibrated"
    if check("hu_calibration", ok, f"-1000 → {f_ok} | -700 → {f_bad}"): n_pass += 1
    else: n_fail += 1

    print("\n=== ring_artifact_index (deve SUBIR com anéis) ===")
    r_clean = ring_artifact_index(make_ct_phantom(sigma_air=5, sigma_body=10))[0]
    r_rings = ring_artifact_index(add_rings(make_ct_phantom(sigma_air=5, sigma_body=10)))[0]
    ok = r_rings > 2 * r_clean
    if check("ring_artifact_index", ok, f"clean={r_clean:.2f} | rings={r_rings:.2f}"): n_pass += 1
    else: n_fail += 1

    print("\n=== streak_index (deve SUBIR com ruído) ===")
    s_low = streak_index(make_ct_phantom(sigma_body=5))[0]
    s_high = streak_index(make_ct_phantom(sigma_body=50))[0]
    ok = s_high > s_low * 3
    if check("streak_index", ok, f"σ=5 → {s_low:.1f} | σ=50 → {s_high:.1f}"): n_pass += 1
    else: n_fail += 1

    print(f"\n=== {n_pass} passed, {n_fail} failed ===")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
