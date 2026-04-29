"""Utilitários para labels e conversões."""
from __future__ import annotations
import numpy as np


def scores_to_classes(scores: np.ndarray, n_classes: int = 3) -> np.ndarray:
    """Converte scores contínuos [0, 100] para classes discretas.
    
    Args:
        scores: array de scores [0, 100]
        n_classes: número de classes (3 = ruim/regular/bom)
    
    Returns:
        array de classes [0, n_classes-1]
    """
    bins = np.linspace(0, 100, n_classes + 1)
    classes = np.digitize(scores, bins) - 1
    classes = np.clip(classes, 0, n_classes - 1)
    return classes


def classes_to_scores(classes: np.ndarray, n_classes: int = 3) -> np.ndarray:
    """Converte classes para score médio da classe."""
    class_centers = np.linspace(0, 100, n_classes * 2 + 1)[1::2]
    return class_centers[classes]


def create_pairs_for_ranking(scores: np.ndarray, n_pairs: int = None) -> tuple:
    """Cria pares de imagens para treinamento de ranking.
    
    Args:
        scores: array de scores
        n_pairs: número de pares (None = todos os pares possíveis)
    
    Returns:
        (indices_A, indices_B, labels) onde label=1 se A>B
    """
    n = len(scores)
    if n_pairs is None:
        n_pairs = min(n * (n - 1) // 2, 10000)
    
    indices_A = []
    indices_B = []
    labels = []
    
    for _ in range(n_pairs):
        i, j = np.random.choice(n, 2, replace=False)
        indices_A.append(i)
        indices_B.append(j)
        labels.append(1 if scores[i] > scores[j] else -1)
    
    return (np.array(indices_A), np.array(indices_B), np.array(labels))
