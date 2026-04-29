"""MIQA Teacher-Student Training — treina CNN usando métricas físicas como teacher.

O teacher são nossas métricas físicas (score unificado de 0-100).
O student é um CNN (ResNet/EfficientNet) que aprende a prever o score.

Uso:
    python -m miqa.ml_models.train <<--modality rx <>> --body_part chest <>> --dataset_path /path/to/images
"""
from __future__ import annotations
import argparse
import json
import random
import time
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, random_split
from torchvision import transforms
from PIL import Image
import cv2

from miqa.ml_models import MIQAModel, register_model
from miqa.anatomy import detect_anatomy, run_anatomy_aware_metrics
from miqa.metrics.universal_v2 import run_all_v2
from miqa.pipelines.build_unified_score import compute_unified_score


def set_seed(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


class TeacherScoreComputer:
    """Computa score teacher a partir de métricas físicas."""
    
    def __init__(self, modality: str, body_part: str):
        self.modality = modality
        self.body_part = body_part
    
    def compute(self, img_path: Path, img_tensor: torch.Tensor) -> float:
        """Computa score unificado para uma imagem.
        
        Args:
            img_path: caminho da imagem original
            img_tensor: tensor [3, H, W] para referência de shape
        
        Returns:
            score float [0, 100]
        """
        try:
            # Carrega imagem original
            img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
            if img is None:
                # Tenta DICOM
                import pydicom
                ds = pydicom.dcmread(img_path)
                img = ds.pixel_array.astype(np.float32)
                if img.ndim == 3:
                    img = img[img.shape[0] // 2]
            
            if img.ndim == 3:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Normaliza
            a, b = float(img.min()), float(img.max())
            img_norm = ((img - a) / max(b - a, 1e-9)).astype(np.float32)
            
            # Métricas universais
            universal = run_all_v2(img_norm)
            
            # Métricas anatomy-aware
            ctx = detect_anatomy(img_path, img=img_norm)
            anatomy = run_anatomy_aware_metrics(ctx, img_norm)
            
            # Combina tudo
            all_metrics = {**universal, **anatomy}
            
            # Computa score unificado (simplificado)
            score = self._compute_unified_score(all_metrics)
            
            return float(np.clip(score, 0, 100))
        except Exception as e:
            print(f"  Teacher falhou para {img_path.name}: {e}")
            return 50.0  # Fallback
    
    def _compute_unified_score(self, metrics: dict) -> float:
        """Score unificado simples baseado nas métricas disponíveis."""
        scores = []
        
        # SNR-like metrics (maior é melhor)
        for key in metrics:
            val = metrics[key].get("value", np.nan)
            if not np.isnan(val):
                # Normaliza para [0, 1] baseado em ranges típicos
                if "snr" in key.lower() or "cnr" in key.lower():
                    scores.append(min(val / 50, 1.0) * 100)
                elif "contrast" in key.lower():
                    scores.append(min(val / 0.5, 1.0) * 100)
                elif "noise" in key.lower() or "mottle" in key.lower():
                    scores.append(max(0, 1 - val / 100) * 100)
                elif "niqe" in key.lower():
                    scores.append(max(0, 1 - val / 20) * 100)
                elif "brisque" in key.lower():
                    scores.append(max(0, 1 - val / 100) * 100)
        
        if not scores:
            return 50.0
        
        return float(np.median(scores))


class MIQADataset(Dataset):
    """Dataset que carrega imagens e scores teacher."""
    
    def __init__(self, image_paths: list[Path], scores: list[float],
                 transform: Optional[transforms.Compose] = None):
        self.paths = image_paths
        self.scores = scores
        self.transform = transform or self._default_transform()
    
    def _default_transform(self):
        return transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], 
                                [0.229, 0.224, 0.225])
        ])
    
    def __len__(self):
        return len(self.paths)
    
    def __getitem__(self, idx):
        path = self.paths[idx]
        score = self.scores[idx]
        
        # Carrega imagem
        img = Image.open(path).convert("RGB")
        if self.transform:
            img = self.transform(img)
        
        return img, torch.tensor(score, dtype=torch.float32)


def prepare_dataset(dataset_path: Path, modality: str, body_part: str,
                    max_images: int = 1000, cache_file: Optional[Path] = None) -> Tuple[list[Path], list[float]]:
    """Prepara dataset com scores teacher.
    
    Args:
        dataset_path: diretório com imagens
        modality: rx, us, ct, mri
        body_part: chest, brain, liver, etc.
        max_images: máximo de imagens a processar
        cache_file: arquivo para cache de scores
    
    Returns:
        (lista de paths, lista de scores)
    """
    # Encontra imagens
    extensions = ["*.jpg", "*.jpeg", "*.png", "*.dcm"]
    image_paths = []
    for ext in extensions:
        image_paths.extend(dataset_path.rglob(ext))
    
    image_paths = sorted(image_paths)[:max_images]
    print(f"Encontradas {len(image_paths)} imagens em {dataset_path}")
    
    # Cache
    if cache_file and cache_file.exists():
        print(f"Carregando scores do cache: {cache_file}")
        cache = json.loads(cache_file.read_text())
        cached_paths = [Path(p) for p in cache["paths"]]
        cached_scores = cache["scores"]
        return cached_paths, cached_scores
    
    # Computa scores teacher
    teacher = TeacherScoreComputer(modality, body_part)
    scores = []
    
    print("Computando scores teacher...")
    for i, path in enumerate(image_paths):
        if i % 50 == 0:
            print(f"  {i}/{len(image_paths)}")
        
        score = teacher.compute(path, None)
        scores.append(score)
    
    # Salva cache
    if cache_file:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache = {
            "paths": [str(p) for p in image_paths],
            "scores": scores,
            "modality": modality,
            "body_part": body_part,
        }
        cache_file.write_text(json.dumps(cache))
    
    return image_paths, scores


def train_model(modality: str, body_part: str, dataset_path: Path,
                backbone: str = "efficientnet_b0", head_type: str = "regression",
                epochs: int = 10, batch_size: int = 32, lr: float = 1e-4,
                val_split: float = 0.2, max_images: int = 1000,
                device: Optional[str] = None, output_name: str = "quality_regressor"):
    """Treina modelo teacher-student.
    
    Args:
        modality: rx, us, ct, mri
        body_part: chest, brain, liver, etc.
        dataset_path: diretório com imagens
        backbone: resnet50 ou efficientnet_b0
        head_type: regression, classification, ranking
        epochs: número de épocas
        batch_size: tamanho do batch
        lr: learning rate
        val_split: fração para validação
        max_images: máximo de imagens
        device: cuda, mps, cpu
        output_name: nome do checkpoint
    """
    set_seed(42)
    
    # Device
    if device is None:
        if torch.cuda.is_available():
            device = "cuda"
        elif torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
    device = torch.device(device)
    print(f"Device: {device}")
    
    # Prepara dataset
    cache_file = Path(f"miqa/ml_models/checkpoints/{modality}/{body_part}/teacher_scores.json")
    image_paths, scores = prepare_dataset(
        dataset_path, modality, body_part, 
        max_images=max_images, cache_file=cache_file
    )
    
    if len(image_paths) < 10:
        raise ValueError(f"Dataset muito pequeno: {len(image_paths)} imagens")
    
    # Estatísticas
    scores_arr = np.array(scores)
    print(f"\nScores teacher — média: {scores_arr.mean():.1f}, "
          f"std: {scores_arr.std():.1f}, "
          f"min: {scores_arr.min():.1f}, max: {scores_arr.max():.1f}")
    
    # Dataset e DataLoader
    dataset = MIQADataset(image_paths, scores)
    
    val_size = int(len(dataset) * val_split)
    train_size = len(dataset) - val_size
    train_ds, val_ds = random_split(dataset, [train_size, val_size])
    
    train_dl = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=2)
    val_dl = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=2)
    
    # Modelo
    model = MIQAModel(backbone=backbone, head_type=head_type, pretrained=True)
    model = model.to(device)
    
    # Loss e optimizer
    if head_type == "regression":
        criterion = nn.MSELoss()
    elif head_type == "classification":
        # Converte scores para classes
        from miqa.ml_models.utils.label_utils import scores_to_classes
        criterion = nn.CrossEntropyLoss()
    else:
        criterion = nn.MarginRankingLoss(margin=0.1)
    
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", patience=3)
    
    # Treinamento
    best_val_loss = float("inf")
    history = {"train_loss": [], "val_loss": [], "val_mae": []}
    
    print(f"\nIniciando treinamento: {modality}/{body_part}")
    print(f"Train: {train_size}, Val: {val_size}")
    
    for epoch in range(epochs):
        # Train
        model.train()
        train_losses = []
        
        for batch_idx, (images, targets) in enumerate(train_dl):
            images = images.to(device)
            targets = targets.to(device)
            
            optimizer.zero_grad()
            outputs = model(images)
            
            if head_type == "ranking":
                # Para ranking, precisamos de pares
                loss = criterion(outputs[:len(outputs)//2], outputs[len(outputs)//2:],
                               torch.ones(len(outputs)//2).to(device))
            else:
                loss = criterion(outputs.squeeze(), targets)
            
            loss.backward()
            optimizer.step()
            
            train_losses.append(loss.item())
            
            if batch_idx % 10 == 0:
                print(f"  Epoch {epoch+1}/{epochs} [{batch_idx}/{len(train_dl)}] "
                      f"Loss: {loss.item():.4f}")
        
        avg_train_loss = np.mean(train_losses)
        
        # Validação
        model.eval()
        val_losses = []
        val_maes = []
        
        with torch.no_grad():
            for images, targets in val_dl:
                images = images.to(device)
                targets = targets.to(device)
                
                outputs = model.predict_score(images)
                
                loss = criterion(outputs, targets)
                val_losses.append(loss.item())
                
                mae = torch.abs(outputs - targets).mean().item()
                val_maes.append(mae)
        
        avg_val_loss = np.mean(val_losses)
        avg_val_mae = np.mean(val_maes)
        
        history["train_loss"].append(avg_train_loss)
        history["val_loss"].append(avg_val_loss)
        history["val_mae"].append(avg_val_mae)
        
        print(f"Epoch {epoch+1}/{epochs} — "
              f"Train Loss: {avg_train_loss:.4f}, "
              f"Val Loss: {avg_val_loss:.4f}, "
              f"Val MAE: {avg_val_mae:.2f}")
        
        scheduler.step(avg_val_loss)
        
        # Salva melhor modelo
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            
            ckpt_dir = Path(f"miqa/ml_models/checkpoints/{modality}/{body_part}")
            ckpt_dir.mkdir(parents=True, exist_ok=True)
            ckpt_path = ckpt_dir / f"{output_name}.pt"
            
            torch.save(model.state_dict(), ckpt_path)
            print(f"  💾 Modelo salvo: {ckpt_path}")
            
            # Registra
            from miqa.ml_models import register_model
            register_model(modality, body_part, output_name, {
                "backbone": backbone,
                "head": head_type,
                "epochs": epochs,
                "batch_size": batch_size,
                "lr": lr,
                "best_val_loss": float(best_val_loss),
                "best_val_mae": float(avg_val_mae),
                "n_train": train_size,
                "n_val": val_size,
            })
    
    print(f"\n✅ Treinamento concluído!")
    print(f"Melhor val loss: {best_val_loss:.4f}")
    
    return model, history


def main():
    ap = argparse.ArgumentParser(description="Treina modelo MIQA teacher-student")
    ap.add_argument("--modality", required=True, choices=["rx", "us", "ct", "mri"])
    ap.add_argument("--body_part", required=True, 
                    help="chest, brain, liver, etc.")
    ap.add_argument("--dataset_path", required=True, type=Path,
                    help="Diretório com imagens")
    ap.add_argument("--backbone", default="efficientnet_b0",
                    choices=["resnet50", "efficientnet_b0"])
    ap.add_argument("--head", default="regression",
                    choices=["regression", "classification", "ranking"])
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch_size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--max_images", type=int, default=1000)
    ap.add_argument("--output_name", default="quality_regressor")
    
    args = ap.parse_args()
    
    model, history = train_model(
        modality=args.modality,
        body_part=args.body_part,
        dataset_path=args.dataset_path,
        backbone=args.backbone,
        head_type=args.head,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        max_images=args.max_images,
        output_name=args.output_name,
    )
    
    # Salva histórico
    history_path = Path(f"miqa/ml_models/checkpoints/{args.modality}/{args.body_part}/training_history.json")
    history_path.write_text(json.dumps(history, indent=2))
    print(f"Histórico salvo: {history_path}")


if __name__ == "__main__":
    main()
