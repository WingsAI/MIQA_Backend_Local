"""Validação sintética MRI."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
from miqa.metrics.mri import nema_snr, ghosting_score, bias_field_score, motion_highfreq


def make_brain_phantom(shape=(256, 256), sigma=0.02, seed=42, ghost_amp=0.0,
                       bias=0.0, hf_noise=0.0):
    """Phantom MRI simples: disco central (tecido) + fundo de ar com ruído."""
    rng = np.random.default_rng(seed)
    h, w = shape
    yy, xx = np.mgrid[:h, :w]
    cy, cx = h // 2, w // 2
    rad = h // 5  # menor pra ghost shifted h/2 não tocar o tecido
    mask = (yy - cy)**2 + (xx - cx)**2 < rad**2
    img = np.full(shape, 0.05, dtype=np.float32)
    img[mask] = 0.7
    # ghost: réplica deslocada FOV/2 do tecido, amplitude 'ghost_amp'
    if ghost_amp > 0:
        shift = h // 2
        ghost_mask_top = np.zeros_like(mask)
        if shift < h:
            ghost_mask_top[:h-shift] = mask[shift:]
        img[ghost_mask_top & ~mask] += ghost_amp
    # bias: rampa linear adicionada apenas dentro do tecido
    if bias > 0:
        ramp = np.linspace(-bias, bias, h)[:, None] * np.ones((1, w))
        img[mask] += ramp[mask]
    img += rng.standard_normal(shape).astype(np.float32) * sigma
    if hf_noise > 0:
        # ruído correlacionado em alta freq pra simular movimento
        nh = rng.standard_normal(shape).astype(np.float32)
        nh = nh - np.mean(nh, axis=0, keepdims=True)  # remove DC
        img[mask] += nh[mask] * hf_noise
    return np.clip(img, 0, 1)


def check(name, cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}: {msg}")
    return cond


def main():
    n_pass = n_fail = 0

    print("=== nema_snr: SOBE com sinal/ruído melhor ===")
    s_low = nema_snr(make_brain_phantom(sigma=0.05))[0]
    s_high = nema_snr(make_brain_phantom(sigma=0.005))[0]
    ok = s_high > 3 * s_low
    if check("nema_snr", ok, f"σ=0.05→SNR={s_low:.1f}  σ=0.005→SNR={s_high:.1f}"): n_pass += 1
    else: n_fail += 1

    print("\n=== ghosting: SOBE com fantasma injetado ===")
    g_clean = ghosting_score(make_brain_phantom())[0]
    g_ghost = ghosting_score(make_brain_phantom(ghost_amp=0.10))[0]
    ok = g_ghost > g_clean + 1.0
    if check("ghosting", ok, f"clean={g_clean:.2f}  ghost(amp=0.10)={g_ghost:.2f}"): n_pass += 1
    else: n_fail += 1

    print("\n=== bias_field: SOBE com bias forte ===")
    b_low = bias_field_score(make_brain_phantom())[0]
    b_high = bias_field_score(make_brain_phantom(bias=0.20))[0]
    ok = b_high > 2 * b_low
    if check("bias_field", ok, f"sem_bias={b_low:.3f}  com_bias={b_high:.3f}"): n_pass += 1
    else: n_fail += 1

    print("\n=== motion_hf: SOBE com ruído de alta freq ===")
    m_low = motion_highfreq(make_brain_phantom(sigma=0.005))[0]
    m_high = motion_highfreq(make_brain_phantom(sigma=0.005, hf_noise=0.05))[0]
    ok = m_high > 1.5 * m_low
    if check("motion_hf", ok, f"limpa={m_low:.4f}  motion={m_high:.4f}"): n_pass += 1
    else: n_fail += 1

    print(f"\n=== {n_pass} passed, {n_fail} failed ===")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
