"""MIQA ML Models — registry e loading de modelos por contexto anatômico.

Uso:
    from miqa.ml_models import get_model, list_available_models
    model = get_model("rx", "chest", "quality_regressor")
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn

from miqa.ml_models.backbones.resnet_quality import ResNet50Quality
from miqa.ml_models.backbones.efficientnet_quality import EfficientNetB0Quality


ROOT = Path(__file__).parent
CHECKPOINTS = ROOT / "checkpoints"
REGISTRY_FILE = ROOT / "model_registry.json"


# Default configs
_DEFAULT_CONFIGS = {
    "backbone": "efficientnet_b0",
    "head": "regression",
    "output_dim": 1,  # regression: 1 score
}


class MIQAModel(nn.Module):
    """Wrapper que combina backbone + head."""
    
    def __init__(self, backbone: str, head_type: str, output_dim: int = 1, 
                 pretrained: bool = True):
        super().__init__()
        self.backbone_name = backbone
        self.head_type = head_type
        
        # Backbone
        if backbone == "resnet50":
            self.backbone = ResNet50Quality(pretrained=pretrained)
            feat_dim = 2048
        elif backbone == "efficientnet_b0":
            self.backbone = EfficientNetB0Quality(pretrained=pretrained)
            feat_dim = 1280
        else:
            raise ValueError(f"Backbone desconhecido: {backbone}")
        
        # Head
        if head_type == "regression":
            from miqa.ml_models.heads.regression_head import RegressionHead
            self.head = RegressionHead(feat_dim, output_dim=output_dim)
        elif head_type == "classification":
            from miqa.ml_models.heads.classification_head import ClassificationHead
            self.head = ClassificationHead(feat_dim, num_classes=output_dim)
        elif head_type == "ranking":
            from miqa.ml_models.heads.ranking_head import RankingHead
            self.head = RankingHead(feat_dim)
        else:
            raise ValueError(f"Head desconhecido: {head_type}")
    
    def forward(self, x):
        features = self.backbone(x)
        return self.head(features)
    
    def predict_score(self, x):
        """Retorna score de qualidade [0, 100]."""
        self.eval()
        with torch.no_grad():
            out = self.forward(x)
            if self.head_type == "regression":
                return torch.clamp(out, 0, 100)
            elif self.head_type == "classification":
                probs = torch.softmax(out, dim=1)
                # Score = média ponderada das classes
                classes = torch.arange(out.shape[1], device=out.device)
                return (probs * classes).sum(dim=1) * (100 / (out.shape[1] - 1))
            else:
                return out


def _load_registry() -> dict:
    """Carrega registry de modelos disponíveis."""
    if REGISTRY_FILE.exists():
        return json.loads(REGISTRY_FILE.read_text())
    return {}


def list_available_models() -> dict:
    """Lista todos os modelos treinados disponíveis."""
    registry = _load_registry()
    models = {}
    
    for modality in ["rx", "us", "ct", "mri"]:
        models[modality] = {}
        mod_dir = CHECKPOINTS / modality
        if not mod_dir.exists():
            continue
        for body_part_dir in mod_dir.iterdir():
            if body_part_dir.is_dir():
                bp = body_part_dir.name
                models[modality][bp] = []
                for ckpt_file in body_part_dir.glob("*.pt"):
                    model_name = ckpt_file.stem
                    info = registry.get(f"{modality}/{bp}/{model_name}", {})
                    models[modality][bp].append({
                        "name": model_name,
                        "path": str(ckpt_file),
                        **info
                    })
    
    return models


def get_model(modality: str, body_part: str, model_name: str = "quality_regressor",
              device: Optional[str] = None) -> Optional[MIQAModel]:
    """Carrega modelo treinado para um contexto anatômico.
    
    Args:
        modality: rx, us, ct, mri
        body_part: chest, brain, liver, etc.
        model_name: nome do checkpoint (sem .pt)
        device: cuda, mps, cpu
    
    Returns:
        MIQAModel carregado ou None se não existir
    """
    ckpt_path = CHECKPOINTS / modality / body_part / f"{model_name}.pt"
    
    if not ckpt_path.exists():
        return None
    
    # Carrega config do registry
    registry = _load_registry()
    config = registry.get(f"{modality}/{body_part}/{model_name}", _DEFAULT_CONFIGS)
    
    # Cria modelo
    model = MIQAModel(
        backbone=config.get("backbone", "efficientnet_b0"),
        head_type=config.get("head", "regression"),
        output_dim=config.get("output_dim", 1),
        pretrained=False  # Não precisa de ImageNet se temos checkpoint
    )
    
    # Carrega pesos
    state_dict = torch.load(ckpt_path, map_location="cpu")
    model.load_state_dict(state_dict)
    
    # Device
    if device is None:
        if torch.cuda.is_available():
            device = "cuda"
        elif torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
    
    model = model.to(device)
    model.eval()
    
    return model


def register_model(modality: str, body_part: str, model_name: str, 
                   config: dict):
    """Registra um modelo no registry."""
    registry = _load_registry()
    registry[f"{modality}/{body_part}/{model_name}"] = config
    REGISTRY_FILE.write_text(json.dumps(registry, indent=2))


__all__ = ["MIQAModel", "get_model", "list_available_models", "register_model"]