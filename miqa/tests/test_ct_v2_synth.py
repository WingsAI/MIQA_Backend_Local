"""Validação sintética CT v2 (slice consistency)."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
from miqa.metrics.ct_v2 import slice_consistency


def make_consistent_volume(n=20, shape=(256, 256), seed=42):
    rng = np.random.default_rng(seed)
    base_air = -1000
    base_body = 40
    yy, xx = np.mgrid[:shape[0], :shape[1]]
    body = (yy - shape[0]//2)**2 + (xx - shape[1]//2)**2 < 70**2
    slices = []
    for i in range(n):
        s = np.full(shape, base_air, dtype=np.float32)
        s[body] = base_body
        s += rng.standard_normal(shape).astype(np.float32) * 10
        slices.append(s)
    return slices


def make_drifty_volume(n=20, shape=(256, 256), seed=42):
    """Volume com μ flutuando (drift severo entre slices)."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[:shape[0], :shape[1]]
    body = (yy - shape[0]//2)**2 + (xx - shape[1]//2)**2 < 70**2
    slices = []
    for i in range(n):
        s = np.full(shape, -1000, dtype=np.float32)
        # corpo com HU oscilando entre slices (drift)
        body_hu = 40 + (i % 4) * 200  # salta 0/200/400/600
        s[body] = body_hu
        s += rng.standard_normal(shape).astype(np.float32) * 10
        slices.append(s)
    return slices


def make_volume_with_anomaly(n=20, shape=(256, 256), seed=42):
    slices = make_consistent_volume(n, shape, seed)
    # injeta 1 slice anômalo (HU multiplicado por 5)
    slices[10] = slices[10] * 5
    return slices


def check(name, cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}: {msg}")
    return cond


def main():
    n_pass = n_fail = 0

    print("=== consistent volume: drift baixo, slice_corr alto ===")
    r = slice_consistency(make_consistent_volume())
    ok = r["mean_hu_drift"] < 30 and r["slice_corr"] > 0.3 and r["anomaly_pct"] < 10
    if check("consistent",
             ok,
             f"drift={r['mean_hu_drift']:.1f}HU corr={r['slice_corr']:.2f} anom={r['anomaly_pct']:.1f}%"):
        n_pass += 1
    else: n_fail += 1

    print("\n=== drifty volume: drift alto detectado ===")
    r = slice_consistency(make_drifty_volume())
    ok = r["mean_hu_drift"] > 50
    if check("drift_detected", ok, f"drift={r['mean_hu_drift']:.1f}HU"): n_pass += 1
    else: n_fail += 1

    print("\n=== volume com anomalia: anomaly_pct > 0 ===")
    r = slice_consistency(make_volume_with_anomaly())
    ok = r["anomaly_pct"] > 0
    if check("anomaly_flagged", ok,
             f"anom={r['anomaly_pct']:.1f}% drift={r['mean_hu_drift']:.0f}"): n_pass += 1
    else: n_fail += 1

    print(f"\n=== {n_pass} passed, {n_fail} failed ===")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
