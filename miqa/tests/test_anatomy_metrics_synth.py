"""Testes sintéticos para métricas anatomy-aware.

Gera imagens sintéticas controladas e verifica se métricas retornam valores esperados.
"""
from __future__ import annotations
import numpy as np
import cv2
import pytest

from miqa.anatomy.metric_registry import ALL_ANATOMY_METRICS
# Import modules to trigger @register decorators
import miqa.anatomy.metrics_rx
import miqa.anatomy.metrics_us
import miqa.anatomy.metrics_ct
import miqa.anatomy.metrics_mri


def _make_uniform(size: tuple[int, int], val: float, noise: float = 0.0) -> np.ndarray:
    """Imagem uniforme com ruído opcional."""
    img = np.full(size, val, dtype=np.float32)
    if noise > 0:
        img += np.random.default_rng(42).normal(0, noise, size).astype(np.float32)
    return np.clip(img, 0, 1)


def _make_gradient(size: tuple[int, int], direction: str = "vertical") -> np.ndarray:
    """Gradiente linear."""
    h, w = size
    if direction == "vertical":
        img = np.linspace(0.2, 0.8, h).reshape(-1, 1)
        img = np.tile(img, (1, w))
    else:
        img = np.linspace(0.2, 0.8, w).reshape(1, -1)
        img = np.tile(img, (h, 1))
    return img.astype(np.float32)


# ========== RX TESTS ==========

def test_rx_chest_lung_symmetry_perfect():
    """Torax simétrico: score próximo de 1.0."""
    fn = ALL_ANATOMY_METRICS["rx_chest.lung_symmetry"]
    img = _make_uniform((512, 512), 0.5, noise=0.05)
    val, extra = fn(img)
    assert val > 0.8, f"Expected high symmetry, got {val}"


def test_rx_chest_lung_symmetry_asymmetric():
    """Torax assimétrico: score menor."""
    fn = ALL_ANATOMY_METRICS["rx_chest.lung_symmetry"]
    img = np.ones((512, 512), dtype=np.float32) * 0.5
    img[:, :256] *= 0.7  # lado esquerdo mais escuro
    val, extra = fn(img)
    assert val < 0.8, f"Expected lower symmetry, got {val}"


def test_rx_chest_inspiration_index():
    """Pulmão com muito ar: índice alto."""
    fn = ALL_ANATOMY_METRICS["rx_chest.inspiration_index"]
    img = np.ones((512, 512), dtype=np.float32) * 0.7
    # Pulmões nas laterais do centro
    img[100:400, 50:200] = 0.05   # pulmão esquerdo
    img[100:400, 312:462] = 0.05  # pulmão direito
    val, extra = fn(img)
    assert val > 0.05, f"Expected lung area, got {val}"


def test_rx_extremity_bone_snr():
    """Extremidade com osso claro e fundo escuro com ruido."""
    fn = ALL_ANATOMY_METRICS["rx_extremity.bone_snr"]
    img = np.ones((512, 512), dtype=np.float32) * 0.1
    img += np.random.default_rng(42).normal(0, 0.01, img.shape).astype(np.float32)
    img[200:300, 200:300] = 0.9  # osso
    val, extra = fn(img)
    assert not np.isnan(val), f"Expected valid SNR, got NaN"
    assert val > 1.0, f"Expected high SNR, got {val}"


def test_rx_skull_sinus_air_score():
    """Crânio com seios escuros."""
    fn = ALL_ANATOMY_METRICS["rx_skull.sinus_air_score"]
    img = np.ones((512, 512), dtype=np.float32) * 0.6
    img[100:150, 200:300] = 0.1  # seios escuros
    val, extra = fn(img)
    assert val > 0.0, f"Expected positive score, got {val}"


# ========== US TESTS ==========

def test_us_abdomen_liver_snr():
    """Fígado uniforme."""
    fn = ALL_ANATOMY_METRICS["us_abdomen.liver_snr"]
    img = _make_uniform((512, 512), 0.5, noise=0.03)
    val, extra = fn(img)
    assert not np.isnan(val), f"Expected valid SNR, got NaN"
    assert val > 5.0, f"Expected high SNR, got {val}"


def test_us_obstetric_gestational_sac_contrast():
    """Saco gestacional escuro com parede clara."""
    fn = ALL_ANATOMY_METRICS["us_obstetric.gestational_sac_contrast"]
    img = np.ones((512, 512), dtype=np.float32) * 0.6
    cv2.circle(img, (256, 256), 80, 0.2, -1)  # saco escuro
    val, extra = fn(img)
    assert not np.isnan(val), f"Expected valid contrast, got NaN"
    assert val > 0.1, f"Expected contrast, got {val}"


def test_us_cardiac_acoustic_window_index():
    """Janela acústica boa (sem sombras)."""
    fn = ALL_ANATOMY_METRICS["us_cardiac.acoustic_window_index"]
    img = _make_uniform((512, 512), 0.5, noise=0.02)
    val, extra = fn(img)
    assert val > 0.5, f"Expected good window, got {val}"


# ========== CT TESTS ==========

def test_ct_brain_sinus_roi_noise():
    """CT cranio: seios com ar (-1000 HU)."""
    fn = ALL_ANATOMY_METRICS["ct_brain.sinus_roi_noise"]
    img = np.ones((512, 512), dtype=np.float32) * 0.5
    hu = np.ones((512, 512), dtype=np.float32) * 40.0
    hu[400:, 150:350] = -1000.0  # seios
    val, extra = fn(img, hu_array=hu)
    assert not np.isnan(val), f"Expected valid noise, got NaN"
    assert val < 100, f"Expected low noise in air, got {val}"


def test_ct_abdomen_liver_spleen_ratio():
    """Fígado e baço com HU similares."""
    fn = ALL_ANATOMY_METRICS["ct_abdomen.liver_spleen_ratio"]
    img = np.ones((512, 512), dtype=np.float32) * 0.5
    hu = np.ones((512, 512), dtype=np.float32) * (-50)
    hu[100:250, :256] = 55.0   # fígado
    hu[100:250, 256:] = 52.0   # baço
    val, extra = fn(img, hu_array=hu)
    assert not np.isnan(val), f"Expected valid ratio, got NaN"
    assert 0.8 < val < 1.2, f"Expected balanced ratio, got {val}"


def test_ct_spine_vertebral_alignment():
    """Coluna alinhada verticalmente."""
    fn = ALL_ANATOMY_METRICS["ct_spine.vertebral_alignment"]
    img = np.ones((512, 512), dtype=np.float32) * 0.5
    hu = np.ones((512, 512), dtype=np.float32) * (-100)
    # Vertebrais empilhados no centro
    for y in range(80, 480, 60):
        hu[y:y+40, 236:276] = 500.0
    val, extra = fn(img, hu_array=hu)
    assert not np.isnan(val), f"Expected valid alignment, got NaN"
    assert val > 0.7, f"Expected good alignment, got {val}"


# ========== MRI TESTS ==========

def test_mri_brain_scalp_snr():
    """Cérebro com escalpo."""
    fn = ALL_ANATOMY_METRICS["mri_brain.scalp_snr"]
    img = np.ones((512, 512), dtype=np.float32) * 0.1
    cv2.circle(img, (256, 256), 200, 0.6, -1)      # cabeça
    cv2.circle(img, (256, 256), 180, 0.5, -1)      # cérebro
    val, extra = fn(img)
    assert not np.isnan(val), f"Expected valid SNR, got NaN"
    assert val > 1.0, f"Expected positive SNR, got {val}"


def test_mri_brain_wm_gm_ratio():
    """Cérebro com WM clara e GM escura."""
    fn = ALL_ANATOMY_METRICS["mri_brain.wm_gm_ratio"]
    img = np.ones((512, 512), dtype=np.float32) * 0.3
    img[150:350, 150:350] = 0.7  # WM
    img[200:300, 200:300] = 0.4  # GM
    val, extra = fn(img)
    assert not np.isnan(val), f"Expected valid ratio, got NaN"
    assert val > 1.0, f"Expected WM brighter than GM, got {val}"


def test_mri_knee_cartilage_homogeneity():
    """Cartilagem uniforme."""
    fn = ALL_ANATOMY_METRICS["mri_knee.cartilage_homogeneity"]
    img = np.ones((512, 512), dtype=np.float32) * 0.3
    img[100:400, 100:400] = 0.5  # tecido mole
    img[200:300, 200:300] = 0.7  # cartilagem
    # Adiciona ruido para criar distribuicao continua
    img += np.random.default_rng(42).normal(0, 0.02, img.shape).astype(np.float32)
    img = np.clip(img, 0, 1)
    val, extra = fn(img)
    assert not np.isnan(val), f"Expected valid score, got NaN"
    assert val > 0.0, f"Expected positive score, got {val}"


def test_mri_spine_disc_vertebra_ratio():
    """Coluna com discos e vertebras."""
    fn = ALL_ANATOMY_METRICS["mri_spine.disc_vertebra_ratio"]
    img = np.ones((512, 512), dtype=np.float32) * 0.3
    # Vertebrais (claras) e discos (escuros) alternados
    for y in range(50, 480, 40):
        img[y:y+25, 200:312] = 0.8  # vertebra
    for y in range(75, 460, 40):
        img[y:y+15, 200:312] = 0.2  # disco
    val, extra = fn(img)
    assert not np.isnan(val), f"Expected valid ratio, got NaN"
    assert val > 1.0, f"Expected vertebra brighter than disc, got {val}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
