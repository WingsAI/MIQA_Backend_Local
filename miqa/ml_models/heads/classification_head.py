"""Head de classificação para classes de qualidade."""
from __future__ import annotations
import torch
import torch.nn as nn


class ClassificationHead(nn.Module):
    """Classificação em N classes de qualidade."""
    
    def __init__(self, input_dim: int, num_classes: int = 3, hidden_dim: int = 512,
                 dropout: float = 0.3):
        super().__init__()
        self.fc = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, num_classes)
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc(x)
