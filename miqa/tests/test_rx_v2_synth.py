"""Validação sintética das métricas RX v2."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
from miqa.metrics.rx_v2 import nps_radial, detect_lung_mask, lung_snr
from miqa.synthetic.degradations import add_gaussian_noise, add_gaussian_blur


def make_uniform(mu=0.5, sigma=0.05, shape=(512, 512), seed=42):
    rng = np.random.default_rng(seed)
    img = np.full(shape, mu, dtype=np.float32) + \
          rng.standard_normal(shape).astype(np.float32) * sigma
    return np.clip(img, 0, 1)


def make_chest_phantom(shape=(512, 512), sigma=0.04, seed=42):
    """Phantom imitando RX de tórax: fundo claro + duas regiões escuras (pulmões)."""
    rng = np.random.default_rng(seed)
    h, w = shape
    img = np.full(shape, 0.7, dtype=np.float32)  # fundo torácico claro
    # pulmões como elipses escuras
    yy, xx = np.mgrid[:h, :w]
    cx_l, cy = w // 3, h // 2
    cx_r = 2 * w // 3
    rad_y, rad_x = h // 4, w // 8
    lung_l = ((yy - cy) / rad_y) ** 2 + ((xx - cx_l) / rad_x) ** 2 < 1
    lung_r = ((yy - cy) / rad_y) ** 2 + ((xx - cx_r) / rad_x) ** 2 < 1
    img[lung_l | lung_r] = 0.25
    img += rng.standard_normal(shape).astype(np.float32) * sigma
    return np.clip(img, 0, 1)


def check(name, cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}: {msg}")
    return cond


def main():
    n_pass = n_fail = 0

    print("=== nps_radial: high_frac SOBE com ruído branco ===")
    img_noisy = make_uniform(sigma=0.10)        # ruído branco → energia espalhada/alta freq
    img_blur = add_gaussian_blur(img_noisy, sigma=4)  # blur → energia desce a baixa freq
    h_noisy = nps_radial(img_noisy)[0]
    h_blur = nps_radial(img_blur)[0]
    ok = h_noisy > h_blur * 1.5
    if check("nps_high_frac", ok,
             f"branco={h_noisy:.3f} | blur={h_blur:.3f} (branco > blur)"):
        n_pass += 1
    else: n_fail += 1

    print("\n=== detect_lung_mask: encontra ~2 regiões escuras ===")
    chest = make_chest_phantom()
    mask = detect_lung_mask(chest)
    area_pct = mask.sum() / mask.size * 100
    ok = 5 < area_pct < 40  # pulmões cobrindo razoavelmente
    if check("detect_lung_mask", ok,
             f"área da máscara={area_pct:.1f}% (esperado 5-40%)"):
        n_pass += 1
    else: n_fail += 1

    print("\n=== lung_snr: cai com mais ruído no pulmão ===")
    chest_low = make_chest_phantom(sigma=0.02)
    chest_high = make_chest_phantom(sigma=0.10)
    snr_low = lung_snr(chest_low)[0]
    snr_high = lung_snr(chest_high)[0]
    ok = (not np.isnan(snr_low)) and (not np.isnan(snr_high)) and snr_high < snr_low / 2
    if check("lung_snr", ok,
             f"σ=0.02→SNR={snr_low:.1f} | σ=0.10→SNR={snr_high:.1f}"):
        n_pass += 1
    else: n_fail += 1

    print(f"\n=== {n_pass} passed, {n_fail} failed ===")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
