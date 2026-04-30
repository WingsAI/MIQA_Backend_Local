"""MIQA Data Augmentation Engine — gera variações sintéticas para treinamento robusto.

Suporta 10+ tipos de degradação e artefatos:
- blur (gaussiano, motion)
- noise (gaussiano, salt & pepper, speckle)
- jpeg compression
- contrast (redução, inversão parcial)
- brightness
- rotation (pequenos ângulos)
- elastic deformation
- ring artifact (CT)
- stripe artifact
- vignetting

Uso:
    from miqa.ml_models.augmentation import Augmenter
    aug = Augmenter()
    variants = aug.generate(image_path, n_variants=5)
"""
from __future__ import annotations
import random
from pathlib import Path
from typing import List, Tuple

import numpy as np
import cv2


class Augmenter:
    """Gera variações degradadas de imagens médicas."""
    
    # Tipos de degradação e seus ranges de severidade
    DEGRADATIONS = {
        # Blur
        'blur_gaussian': (0.1, 1.0),      # sigma
        'blur_motion': (0.1, 0.5),         # fração do kernel
        
        # Noise
        'noise_gaussian': (0.01, 0.08),    # std
        'noise_salt_pepper': (0.001, 0.02), # densidade
        'noise_speckle': (0.01, 0.05),     # std
        
        # Compression
        'jpeg': (10, 60),                   # quality (menor = pior)
        
        # Intensidade
        'contrast_low': (0.3, 0.7),        # alpha
        'contrast_high': (1.3, 1.8),       # alpha
        'brightness_dark': (-0.3, -0.1),   # beta
        'brightness_bright': (0.1, 0.3),   # beta
        
        # Geométrico
        'rotation': (-5, 5),               # graus
        'scale': (0.9, 1.1),               # fator
        
        # Artefatos
        'ring_artifact': (0.05, 0.2),      # intensidade
        'stripe_artifact': (0.05, 0.15),   # intensidade
        'vignetting': (0.1, 0.4),          # intensidade
    }
    
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        np.random.seed(seed)
    
    def apply(self, img: np.ndarray, deg_type: str, severity: float) -> np.ndarray:
        """Aplica uma degradação específica.
        
        Args:
            img: imagem [0,1] float32
            deg_type: tipo de degradação
            severity: 0.0-1.0 (normalizado)
        
        Returns:
            imagem degradada [0,1]
        """
        if deg_type == 'blur_gaussian':
            sigma = 0.5 + severity * 4.5
            k = int(sigma * 3) * 2 + 1
            return cv2.GaussianBlur(img, (k, k), sigma)
        
        elif deg_type == 'blur_motion':
            size = int(3 + severity * 20)
            kernel = np.zeros((size, size))
            kernel[size//2, :] = 1.0 / size
            return cv2.filter2D(img, -1, kernel)
        
        elif deg_type == 'noise_gaussian':
            std = 0.01 + severity * 0.1
            noise = np.random.normal(0, std, img.shape)
            return np.clip(img + noise, 0, 1)
        
        elif deg_type == 'noise_salt_pepper':
            density = 0.001 + severity * 0.03
            noisy = img.copy()
            # Salt
            salt = np.random.random(img.shape) < density / 2
            noisy[salt] = 1.0
            # Pepper
            pepper = np.random.random(img.shape) < density / 2
            noisy[pepper] = 0.0
            return noisy
        
        elif deg_type == 'noise_speckle':
            std = 0.01 + severity * 0.08
            noise = np.random.normal(0, std, img.shape)
            return np.clip(img * (1 + noise), 0, 1)
        
        elif deg_type == 'jpeg':
            quality = int(95 - severity * 85)
            img_8bit = (img * 255).astype(np.uint8)
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), max(quality, 1)]
            _, enc = cv2.imencode(".jpg", img_8bit, encode_param)
            dec = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
            return dec.astype(np.float32) / 255.0
        
        elif deg_type == 'contrast_low':
            alpha = 1.0 - severity * 0.7
            return np.clip((img - 0.5) * alpha + 0.5, 0, 1)
        
        elif deg_type == 'contrast_high':
            alpha = 1.0 + severity * 0.8
            return np.clip((img - 0.5) * alpha + 0.5, 0, 1)
        
        elif deg_type == 'brightness_dark':
            beta = -severity * 0.4
            return np.clip(img + beta, 0, 1)
        
        elif deg_type == 'brightness_bright':
            beta = severity * 0.4
            return np.clip(img + beta, 0, 1)
        
        elif deg_type == 'rotation':
            angle = (severity - 0.5) * 10  # -5 a +5 graus
            h, w = img.shape
            M = cv2.getRotationMatrix2D((w/2, h/2), angle, 1.0)
            return cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)
        
        elif deg_type == 'scale':
            scale = 0.95 + severity * 0.1
            h, w = img.shape
            new_h, new_w = int(h * scale), int(w * scale)
            resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            # Centraliza com padding
            result = np.zeros_like(img)
            y_offset = (h - new_h) // 2
            x_offset = (w - new_w) // 2
            result[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
            return result
        
        elif deg_type == 'ring_artifact':
            # Artefato em anel (comum em CT)
            h, w = img.shape
            center = (w // 2, h // 2)
            Y, X = np.ogrid[:h, :w]
            dist = np.sqrt((X - center[0])**2 + (Y - center[1])**2)
            
            # Cria anéis periódicos
            rings = np.sin(dist / (10 + severity * 40)) * severity * 0.2
            return np.clip(img + rings, 0, 1)
        
        elif deg_type == 'stripe_artifact':
            # Listras verticais
            intensity = severity * 0.15
            stripe_pattern = np.ones_like(img)
            stripe_width = int(5 + severity * 20)
            for i in range(0, img.shape[1], stripe_width * 2):
                stripe_pattern[:, i:i+stripe_width] = 1.0 - intensity
            return np.clip(img * stripe_pattern, 0, 1)
        
        elif deg_type == 'vignetting':
            # Escurecimento nas bordas
            h, w = img.shape
            center = (w // 2, h // 2)
            Y, X = np.ogrid[:h, :w]
            dist = np.sqrt((X - center[0])**2 + (Y - center[1])**2)
            max_dist = np.sqrt(center[0]**2 + center[1]**2)
            
            vignette = 1.0 - (dist / max_dist) * severity * 0.5
            return np.clip(img * vignette, 0, 1)
        
        return img
    
    def generate(self, img: np.ndarray, n_variants: int = 5) -> List[Tuple[np.ndarray, str, float]]:
        """Gera N variantes degradadas de uma imagem.
        
        Returns:
            lista de (imagem_degradada, tipo_degradação, severidade)
        """
        variants = []
        
        # Sempre inclui a imagem original
        variants.append((img, 'original', 0.0))
        
        # Gera variantes aleatórias
        deg_types = list(self.DEGRADATIONS.keys())
        
        for _ in range(n_variants):
            deg_type = self.rng.choice(deg_types)
            severity = self.rng.random()  # 0.0 a 1.0
            
            img_deg = self.apply(img, deg_type, severity)
            variants.append((img_deg, deg_type, severity))
        
        return variants
    
    def generate_progressive(self, img: np.ndarray, n_levels: int = 5) -> List[Tuple[np.ndarray, str, float]]:
        """Gera variações progressivamente piores (útil para análise).
        
        Args:
            n_levels: número de níveis de degradação
        
        Returns:
            lista de (imagem, tipo, severidade) do melhor ao pior
        """
        variants = []
        
        # Original
        variants.append((img, 'original', 0.0))
        
        # Degradações progressivas
        deg_types = ['blur_gaussian', 'noise_gaussian', 'jpeg', 'contrast_low', 'ring_artifact']
        
        for i, deg_type in enumerate(deg_types[:n_levels-1]):
            severity = (i + 1) / n_levels
            img_deg = self.apply(img, deg_type, severity)
            variants.append((img_deg, deg_type, severity))
        
        return variants


def test_augmentation():
    """Testa o augmenter."""
    import matplotlib.pyplot as plt
    
    # Cria imagem sintética simples
    img = np.ones((256, 256), dtype=np.float32) * 0.5
    cv2.circle(img, (128, 128), 60, 0.8, -1)
    
    aug = Augmenter()
    variants = aug.generate(img, n_variants=8)
    
    fig, axes = plt.subplots(3, 3, figsize=(12, 12))
    axes = axes.flatten()
    
    for i, (img_deg, deg_type, severity) in enumerate(variants[:9]):
        axes[i].imshow(img_deg, cmap='gray', vmin=0, vmax=1)
        axes[i].set_title(f'{deg_type}\nsev={severity:.2f}')
        axes[i].axis('off')
    
    plt.tight_layout()
    plt.savefig('test_augmentation.png', dpi=150)
    print("Salvo: test_augmentation.png")


if __name__ == "__main__":
    test_augmentation()
