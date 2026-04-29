"""Registry de métricas anatomy-aware.

Mapeia AnatomicalContext → funções de métrica específicas.
Cada métrica retorna (valor, dict_extras).
"""
from __future__ import annotations
import importlib
from typing import Callable

from miqa.anatomy.detector import AnatomicalContext, BodyPart

# Registry: nome -> função
ALL_ANATOMY_METRICS: dict[str, Callable] = {}


def register(name: str):
    """Decorator para registrar métrica."""
    def decorator(fn):
        ALL_ANATOMY_METRICS[name] = fn
        return fn
    return decorator


def _load_all_metrics():
    """Importa todos os módulos de métricas para registrar automaticamente."""
    modules = [
        "miqa.anatomy.metrics_rx",
        "miqa.anatomy.metrics_us",
        "miqa.anatomy.metrics_ct",
        "miqa.anatomy.metrics_mri",
    ]
    for mod in modules:
        try:
            importlib.import_module(mod)
        except ImportError as e:
            print(f"Warning: could not import {mod}: {e}")


# Mapping: (modality, body_part) -> list of metric names
_RECOMMENDATIONS = {
    # RX
    ("rx", BodyPart.CHEST): [
        "rx_chest.lung_symmetry",
        "rx_chest.inspiration_index",
        "rx_chest.mediastinum_width",
        "rx_chest.rotation_angle",
    ],
    ("rx", BodyPart.EXTREMITY): [
        "rx_extremity.bone_snr",
        "rx_extremity.alignment_score",
        "rx_extremity.bone_penetration",
    ],
    ("rx", BodyPart.SKULL): [
        "rx_skull.penetration_index",
        "rx_skull.sinus_air_score",
    ],
    ("rx", BodyPart.ABDOMEN): [
        "rx_abdomen.nps_fat",
        "rx_abdomen.free_air_detector",
    ],
    # US
    ("us", BodyPart.LIVER): [
        "us_abdomen.liver_snr",
        "us_abdomen.vessel_shadow_ratio",
    ],
    ("us", BodyPart.OBSTETRIC): [
        "us_obstetric.gestational_sac_contrast",
        "us_obstetric.amniotic_fluid_uniformity",
    ],
    ("us", BodyPart.VASCULAR): [
        "us_vascular.vessel_filling_index",
    ],
    ("us", BodyPart.MSK): [
        "us_msk.fiber_orientation",
        "us_msk.tendon_fibril_score",
    ],
    ("us", BodyPart.CARDIAC): [
        "us_cardiac.acoustic_window_index",
        "us_cardiac.chamber_contrast",
    ],
    # CT
    ("ct", BodyPart.BRAIN): [
        "ct_brain.sinus_roi_noise",
        "ct_brain.window_bimodal_check",
    ],
    ("ct", BodyPart.CHEST): [
        "ct_chest.lung_volume_variance",
        "ct_chest.respiratory_motion_index",
    ],
    ("ct", BodyPart.ABDOMEN): [
        "ct_abdomen.liver_spleen_ratio",
        "ct_abdomen.metal_streak_detector",
    ],
    ("ct", BodyPart.SPINE): [
        "ct_spine.vertebral_alignment",
    ],
    # MRI
    ("mri", BodyPart.BRAIN): [
        "mri_brain.scalp_snr",
        "mri_brain.wm_gm_ratio",
        "mri_brain.flow_artifact_score",
    ],
    ("mri", BodyPart.KNEE): [
        "mri_knee.cartilage_homogeneity",
        "mri_knee.meniscus_contrast",
    ],
    ("mri", BodyPart.SPINE): [
        "mri_spine.disc_vertebra_ratio",
    ],
    ("mri", BodyPart.ABDOMEN): [
        "mri_abdomen.adc_consistency",
    ],
}


def get_recommended_metrics(ctx: AnatomicalContext) -> list[str]:
    """Retorna métricas recomendadas para o contexto."""
    key = (ctx.modality, ctx.body_part)
    return _RECOMMENDATIONS.get(key, [])


def run_anatomy_aware_metrics(ctx: AnatomicalContext, img, **kwargs) -> dict:
    """Roda todas as métricas recomendadas para o contexto.

    Args:
        ctx: AnatomicalContext
        img: imagem normalizada [0,1] ou HU (conforme métrica)
        **kwargs: extras (ex: hu_array para CT)

    Returns:
        dict {metric_name: {"value": ..., ...}}
    """
    _load_all_metrics()
    metrics = get_recommended_metrics(ctx)
    results = {}
    for name in metrics:
        fn = ALL_ANATOMY_METRICS.get(name)
        if fn is None:
            continue
        try:
            v, extra = fn(img, **kwargs)
            results[name] = {"value": v, **extra}
        except Exception as e:
            results[name] = {"value": float("nan"), "error": str(e)[:120]}
    return results
