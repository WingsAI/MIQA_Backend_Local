"""Validação das métricas RX com phantoms de propriedade conhecida.

Cada teste:
  - constrói phantom com parâmetro X conhecido (ex.: ruído σ específico)
  - aplica métrica
  - verifica que o valor retornado responde como esperado a variações de X
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
from miqa.metrics.rx import (
    snr_homogeneous, cnr_dark_bright, exposure_proxy, edge_sharpness,
    find_homogeneous_roi,
)
from miqa.synthetic.degradations import add_gaussian_blur


def make_two_region_phantom(mu_dark=0.3, mu_bright=0.7, sigma_noise=0.02,
                            shape=(512, 512), seed=42):
    """Phantom de duas regiões homogêneas + ruído gaussiano."""
    rng = np.random.default_rng(seed)
    h, w = shape
    img = np.full(shape, mu_dark, dtype=np.float32)
    img[:, w // 2:] = mu_bright  # metade direita clara
    img += rng.standard_normal(shape).astype(np.float32) * sigma_noise
    return np.clip(img, 0, 1)


def check(name, cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}: {msg}")
    return cond


def main():
    n_pass = n_fail = 0

    print("=== SNR (deve CAIR com mais ruído) ===")
    snr_low = snr_homogeneous(make_two_region_phantom(sigma_noise=0.005))[0]
    snr_high = snr_homogeneous(make_two_region_phantom(sigma_noise=0.05))[0]
    ok = snr_high < snr_low / 2
    if check("snr_homogeneous", ok, f"σ=0.005 → SNR={snr_low:.1f} | σ=0.05 → SNR={snr_high:.1f}"):
        n_pass += 1
    else:
        n_fail += 1

    print("\n=== CNR (deve SUBIR com mais separação dark/bright) ===")
    cnr_low = cnr_dark_bright(make_two_region_phantom(mu_dark=0.45, mu_bright=0.55))[0]
    cnr_high = cnr_dark_bright(make_two_region_phantom(mu_dark=0.2, mu_bright=0.8))[0]
    ok = cnr_high > 2 * cnr_low
    if check("cnr_dark_bright", ok, f"Δμ=0.10 → CNR={cnr_low:.1f} | Δμ=0.60 → CNR={cnr_high:.1f}"):
        n_pass += 1
    else:
        n_fail += 1

    print("\n=== exposure_proxy (deve flagar correto) ===")
    img_under = make_two_region_phantom(mu_dark=0.05, mu_bright=0.10)
    img_ok = make_two_region_phantom(mu_dark=0.3, mu_bright=0.5)
    img_over = make_two_region_phantom(mu_dark=0.85, mu_bright=0.95)
    flags = [exposure_proxy(im)[1]["flag"] for im in (img_under, img_ok, img_over)]
    ok = flags == ["underexposed", "ok", "overexposed"]
    if check("exposure_proxy", ok, f"flags={flags}"): n_pass += 1
    else: n_fail += 1

    print("\n=== edge_sharpness (deve CAIR com blur) ===")
    # phantom com várias bordas (grid) pra p99 ter sinal suficiente
    base = np.full((512, 512), 0.3, dtype=np.float32)
    for i in range(0, 512, 32):
        base[i:i+8, :] = 0.8
        base[:, i:i+8] = 0.8
    blurred = add_gaussian_blur(base, sigma=3)
    s_base = edge_sharpness(base)[0]
    s_blur = edge_sharpness(blurred)[0]
    ok = s_blur < 0.5 * s_base
    ratio = s_blur / max(s_base, 1e-6)
    if check("edge_sharpness", ok, f"base={s_base:.1f} blur={s_blur:.1f} ratio={ratio:.3f}"):
        n_pass += 1
    else: n_fail += 1

    print("\n=== find_homogeneous_roi (deve preferir região sem borda) ===")
    img = make_two_region_phantom(mu_dark=0.2, mu_bright=0.8, sigma_noise=0.01)
    y, x = find_homogeneous_roi(img, size=64)
    # ROI homogênea escolhida deve estar inteira em uma das metades, não cruzando a borda
    crosses_border = (x < img.shape[1] // 2 < x + 64)
    ok = not crosses_border
    if check("find_homogeneous_roi", ok, f"roi=({x},{y}) | cruza borda? {crosses_border}"):
        n_pass += 1
    else: n_fail += 1

    print(f"\n=== {n_pass} passed, {n_fail} failed ===")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
