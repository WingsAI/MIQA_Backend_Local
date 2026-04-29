"""EfficientNet-B0 adaptado para Image Quality Assessment.

Remove a camada classifier final e expõe features de 1280-dim.
"""
from __future__ import annotations
import torch
import torch.nn as nn
from torchvision import models


class EfficientNetB0Quality(nn.Module):
    """EfficientNet-B0 backbone para IQA."""
    
    def __init__(self, pretrained: bool = True):
        super().__init__()
        weights = models.EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None
        effnet = models.efficientnet_b0(weights=weights)
        
        # Remove a camada classifier
        self.features = effnet.features
        self.avgpool = nn.AdaptiveAvgPool2d(1)
        self.feature_dim = 1280
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Input: [B, 3, H, W], Output: [B, 1280]."""
        x = self.features(x)
        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        return x
    
    @property
    def output_dim(self) -> int:
        return self.feature_dim
