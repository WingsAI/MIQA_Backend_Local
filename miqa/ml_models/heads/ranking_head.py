"""Head de ranking para aprendizado por pares."""
from __future__ import annotations
import torch
import torch.nn as nn


class RankingHead(nn.Module):
    """Scoring function para ranking.
    
    Output é um score bruto; para treinar ranking, comparamos dois outputs.
    """
    
    def __init__(self, input_dim: int, hidden_dim: int = 512, dropout: float = 0.3):
        super().__init__()
        self.fc = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1)
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc(x).squeeze(-1)
