"""Validação sintética: cada métrica responde da forma esperada às degradações.

Rode com:  python -m miqa.tests.test_universal_synth
ou:        pytest miqa/tests/test_universal_synth.py -v
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from miqa.metrics.universal import (
    laplacian_var, tenengrad, shannon_entropy, rms_contrast,
    clipping_pct, dynamic_range_usage,
)
from miqa.synthetic.degradations import (
    make_phantom, add_gaussian_blur, add_gaussian_noise,
    reduce_contrast, clip_intensity,
)


def _v(fn, img):
    return fn(img)[0]


def check(name: str, cond: bool, msg: str):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}: {msg}")
    return cond


def main():
    img = make_phantom()
    n_pass = n_fail = 0

    print("=== nitidez (deve CAIR com blur) ===")
    base_lap = _v(laplacian_var, img)
    blur_lap = _v(laplacian_var, add_gaussian_blur(img, sigma=3))
    base_ten = _v(tenengrad, img)
    blur_ten = _v(tenengrad, add_gaussian_blur(img, sigma=3))
    for name, base, blur in [("laplacian_var", base_lap, blur_lap),
                             ("tenengrad", base_ten, blur_ten)]:
        ok = blur < 0.5 * base
        msg = f"base={base:.2f} blur={blur:.2f} ratio={blur/base:.3f}"
        if check(name, ok, msg): n_pass += 1
        else: n_fail += 1

    print("\n=== contraste (deve CAIR ao comprimir intensidade) ===")
    base_c = _v(rms_contrast, img)
    flat_c = _v(rms_contrast, reduce_contrast(img, factor=0.2))
    ok = flat_c < 0.5 * base_c
    if check("rms_contrast", ok, f"base={base_c:.4f} flat={flat_c:.4f}"): n_pass += 1
    else: n_fail += 1

    base_dr = _v(dynamic_range_usage, img)
    flat_dr = _v(dynamic_range_usage, reduce_contrast(img, factor=0.2))
    ok = flat_dr < 0.5 * base_dr
    if check("dynamic_range", ok, f"base={base_dr:.4f} flat={flat_dr:.4f}"): n_pass += 1
    else: n_fail += 1

    print("\n=== entropia (deve SUBIR com ruído) ===")
    base_e = _v(shannon_entropy, img)
    noisy_e = _v(shannon_entropy, add_gaussian_noise(img, std=0.2))
    ok = noisy_e > base_e
    if check("entropy", ok, f"base={base_e:.3f} noisy={noisy_e:.3f}"): n_pass += 1
    else: n_fail += 1

    print("\n=== clipping (deve SUBIR com saturação forçada) ===")
    base_cl = _v(clipping_pct, img)
    sat_cl = _v(clipping_pct, clip_intensity(img, low=0.3, high=0.7))
    ok = sat_cl > base_cl + 5  # pelo menos +5pp
    if check("clipping_pct", ok, f"base={base_cl:.2f}% sat={sat_cl:.2f}%"): n_pass += 1
    else: n_fail += 1

    print(f"\n=== {n_pass} passed, {n_fail} failed ===")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
