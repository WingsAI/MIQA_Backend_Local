"""Validação das métricas US contra phantoms com propriedades conhecidas."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
from miqa.metrics.us import speckle_snr, shadowing_index, depth_of_penetration, gain_saturation


def make_us_uniform(mu=0.5, sigma=0.05, shape=(400, 400), seed=42):
    """Phantom US uniforme + ruído gaussiano (proxy de speckle)."""
    rng = np.random.default_rng(seed)
    img = np.full(shape, mu, dtype=np.float32)
    img += rng.standard_normal(shape).astype(np.float32) * sigma
    return np.clip(img, 0, 1)


def make_us_with_shadow(mu=0.5, sigma=0.05, shadow_cols=(150, 200),
                        shape=(400, 400), seed=42):
    img = make_us_uniform(mu=mu, sigma=sigma, shape=shape, seed=seed)
    h, w = shape
    # sombra: colunas escuras a partir do meio da imagem (atrás de "estrutura")
    img[h//2:, shadow_cols[0]:shadow_cols[1]] *= 0.1
    return np.clip(img, 0, 1)


def make_us_with_attenuation(mu_top=0.7, decay=0.005, sigma=0.03,
                             shape=(400, 400), seed=42):
    """Sinal cai exponencialmente com profundidade — atenuação típica de US."""
    rng = np.random.default_rng(seed)
    h, w = shape
    depths = np.arange(h)
    profile = mu_top * np.exp(-decay * depths)
    img = np.tile(profile[:, None], (1, w)).astype(np.float32)
    img += rng.standard_normal(shape).astype(np.float32) * sigma
    return np.clip(img, 0, 1)


def check(name, cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}: {msg}")
    return cond


def main():
    n_pass = n_fail = 0

    print("=== speckle_snr (deve CAIR com mais ruído) ===")
    snr_low = speckle_snr(make_us_uniform(sigma=0.02))[0]
    snr_high = speckle_snr(make_us_uniform(sigma=0.15))[0]
    ok = snr_high < snr_low / 3
    if check("speckle_snr", ok, f"σ=0.02 → SNR={snr_low:.2f} | σ=0.15 → SNR={snr_high:.2f}"): n_pass += 1
    else: n_fail += 1

    print("\n=== shadowing_index (deve SUBIR com sombra) ===")
    s_clean = shadowing_index(make_us_uniform())[0]
    s_shadow = shadowing_index(make_us_with_shadow())[0]
    ok = s_shadow > s_clean + 0.05
    if check("shadowing_index", ok, f"clean={s_clean:.2f} shadow={s_shadow:.2f}"): n_pass += 1
    else: n_fail += 1

    print("\n=== depth_of_penetration (deve CAIR com mais atenuação) ===")
    dop_low = depth_of_penetration(make_us_with_attenuation(decay=0.002))[0]
    dop_high = depth_of_penetration(make_us_with_attenuation(decay=0.02))[0]
    ok = dop_high < dop_low - 0.1
    if check("depth_of_penetration", ok, f"baixa atten={dop_low:.2f} | alta atten={dop_high:.2f}"): n_pass += 1
    else: n_fail += 1

    print("\n=== gain_saturation (deve flagar gain alto) ===")
    img_ok = make_us_uniform(mu=0.5, sigma=0.05)
    img_sat = make_us_uniform(mu=0.92, sigma=0.05)
    f_ok = gain_saturation(img_ok)[1]["flag"]
    f_sat = gain_saturation(img_sat)[1]["flag"]
    ok = f_ok == "ok" and f_sat == "gain_too_high"
    if check("gain_saturation", ok, f"normal={f_ok} | saturado={f_sat}"): n_pass += 1
    else: n_fail += 1

    print(f"\n=== {n_pass} passed, {n_fail} failed ===")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
