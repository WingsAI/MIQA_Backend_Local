"""MIQA Anatomy-Aware Metrics — routing de métricas por contexto anatômico.

Uso:
    from miqa.anatomy import detect_anatomy, get_metrics_for_context
    ctx = detect_anatomy(path, img=img_norm, hu_array=hu)
    metrics = get_metrics_for_context(ctx)  # lista de nomes
    results = run_anatomy_aware_metrics(ctx, img)  # dict com resultados
"""
from miqa.anatomy.detector import (
    detect_anatomy,
    get_metrics_for_context,
    AnatomicalContext,
    BodyPart,
    Laterality,
    View,
)
from miqa.anatomy.metric_registry import (
    run_anatomy_aware_metrics,
    ALL_ANATOMY_METRICS,
)

__all__ = [
    "detect_anatomy",
    "get_metrics_for_context",
    "run_anatomy_aware_metrics",
    "AnatomicalContext",
    "BodyPart",
    "Laterality",
    "View",
    "ALL_ANATOMY_METRICS",
]