"""Head de regressão para score de qualidade [0, 100]."""
from __future__ import annotations
import torch
import torch.nn as nn


class RegressionHead(nn.Module):
    """Regressão de score contínuo."""
    
    def __init__(self, input_dim: int, hidden_dim: int = 512, output_dim: int = 1,
                 dropout: float = 0.3):
        super().__init__()
        self.fc = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, output_dim),
            nn.Sigmoid()  # Output [0, 1]
        )
        self.scale = 100.0  # Escala para [0, 100]
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc(x) * self.scale
