"""ResNet50 adaptado para Image Quality Assessment.

Remove a camada FC final e expõe features de 2048-dim.
"""
from __future__ import annotations
import torch
import torch.nn as nn
from torchvision import models


class ResNet50Quality(nn.Module):
    """ResNet50 backbone para IQA."""
    
    def __init__(self, pretrained: bool = True):
        super().__init__()
        weights = models.ResNet50_Weights.IMAGENET1K_V2 if pretrained else None
        resnet = models.resnet50(weights=weights)
        
        # Remove a camada FC final
        self.features = nn.Sequential(*list(resnet.children())[:-1])
        self.feature_dim = 2048
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Input: [B, 3, H, W], Output: [B, 2048]."""
        x = self.features(x)
        x = torch.flatten(x, 1)
        return x
    
    @property
    def output_dim(self) -> int:
        return self.feature_dim
