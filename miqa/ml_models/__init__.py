"""MIQA ML Models — Lightweight CPU models for Image Quality Assessment.

REGRA: Nenhuma rede neural. Apenas modelos leves em CPU:
  - Random Forest
  - XGBoost (opcional)
  - Ridge Regression (fallback)

Uso:
    from miqa.ml_models import predict_quality, list_available_models
    score = predict_quality(path, modality="rx", body_part="chest")
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

import numpy as np

from miqa.ml_models.train_lightweight import (
    load_model,
    predict_quality,
    extract_features,
)


ROOT = Path(__file__).parent
CHECKPOINTS = ROOT / "checkpoints"


def list_available_models() -> dict:
    """Lista todos os modelos treinados disponíveis."""
    models = {}
    
    if not CHECKPOINTS.exists():
        return models
    
    for modality in ["rx", "us", "ct", "mri"]:
        models[modality] = {}
        mod_dir = CHECKPOINTS / modality
        if not mod_dir.exists():
            continue
        for body_part_dir in mod_dir.iterdir():
            if body_part_dir.is_dir():
                bp = body_part_dir.name
                models[modality][bp] = []
                
                for meta_file in body_part_dir.glob("*_metadata.json"):
                    model_type = meta_file.stem.replace("_metadata", "")
                    meta = json.loads(meta_file.read_text())
                    models[modality][bp].append({
                        "name": model_type,
                        "val_mae": meta.get("val_mae", "N/A"),
                        "val_r2": meta.get("val_r2", "N/A"),
                        "n_samples": meta.get("n_samples", "N/A"),
                        "n_features": meta.get("n_features", "N/A"),
                    })
    
    return models


def get_model_info(modality: str, body_part: str, model_type: str = "rf") -> Optional[dict]:
    """Retorna informações de um modelo."""
    data = load_model(modality, body_part, model_type)
    if data is None:
        return None
    return {
        "model_type": data.get("model_type"),
        "val_mae": data.get("val_mae"),
        "val_r2": data.get("val_r2"),
        "n_samples": data.get("n_samples"),
        "n_features": data.get("n_features"),
        "feature_names": data.get("feature_names", []),
    }


__all__ = [
    "predict_quality",
    "list_available_models",
    "get_model_info",
    "load_model",
    "extract_features",
]