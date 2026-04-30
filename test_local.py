#!/usr/bin/env python3
"""Script para testar modelos localmente.

Uso:
    python test_local.py --image path/to/image.png --modality rx --body_part chest
"""
import argparse
from pathlib import Path
import time

import cv2
import numpy as np

from miqa.ml_models import predict_quality, list_available_models


def test_model_loading():
    """Testa carregamento de todos os modelos."""
    print("=" * 70)
    print("TESTE 1: CARREGAMENTO DE MODELOS")
    print("=" * 70)
    
    models = list_available_models()
    total = 0
    
    for modality, body_parts in models.items():
        for body_part, model_list in body_parts.items():
            for model_info in model_list:
                print(f"✅ {modality}/{body_part}: {model_info['name']} "
                      f"(MAE={model_info.get('val_mae', 'N/A')})")
                total += 1
    
    print(f"\nTotal de modelos carregados: {total}")
    return total > 0


def test_prediction(image_path: Path, modality: str, body_part: str):
    """Testa predição em uma imagem."""
    print("\n" + "=" * 70)
    print("TESTE 2: PREDIÇÃO EM IMAGEM REAL")
    print("=" * 70)
    
    print(f"Imagem: {image_path}")
    print(f"Modality: {modality}, Body Part: {body_part}")
    
    # Carrega imagem
    img = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        print("❌ Erro ao carregar imagem")
        return False
    
    print(f"Dimensões: {img.shape}")
    
    # Prediz
    t0 = time.time()
    score = predict_quality(image_path, modality=modality, body_part=body_part)
    elapsed = (time.time() - t0) * 1000
    
    if score is None:
        print("❌ Modelo não encontrado ou erro na predição")
        print("   Usando fallback heurístico...")
        
        from miqa.ml_models.train_lightweight import extract_features, compute_teacher_score
        features = extract_features(image_path, modality)
        score = compute_teacher_score(features)
        print(f"   Score heurístico: {score:.1f}")
    else:
        print(f"✅ Score predito: {score:.1f}/100")
    
    print(f"⏱️  Tempo: {elapsed:.1f}ms")
    
    return score is not None


def test_batch_predictions(dataset_path: Path, modality: str, body_part: str, n_samples: int = 10):
    """Testa predição em lote."""
    print("\n" + "=" * 70)
    print("TESTE 3: PREDIÇÃO EM LOTE")
    print("=" * 70)
    
    image_paths = []
    for ext in ["*.jpg", "*.jpeg", "*.png"]:
        image_paths.extend(dataset_path.rglob(ext))
    
    image_paths = sorted(image_paths)[:n_samples]
    print(f"Amostras: {len(image_paths)}")
    
    scores = []
    times = []
    
    for img_path in image_paths:
        t0 = time.time()
        score = predict_quality(img_path, modality=modality, body_part=body_part)
        elapsed = (time.time() - t0) * 1000
        
        if score is not None:
            scores.append(score)
            times.append(elapsed)
            print(f"  {img_path.name:30s} → {score:5.1f} ({elapsed:5.1f}ms)")
    
    if scores:
        print(f"\nEstatísticas:")
        print(f"  Média:  {np.mean(scores):.1f}")
        print(f"  Std:    {np.std(scores):.1f}")
        print(f"  Min:    {np.min(scores):.1f}")
        print(f"  Max:    {np.max(scores):.1f}")
        print(f"  Tempo médio: {np.mean(times):.1f}ms")
    
    return len(scores) > 0


def main():
    ap = argparse.ArgumentParser(description="Testa modelos MIQA localmente")
    ap.add_argument("--image", type=Path, help="Imagem para testar")
    ap.add_argument("--dataset", type=Path, help="Diretório para teste em lote")
    ap.add_argument("--modality", default="rx", choices=["rx", "us", "ct", "mri"])
    ap.add_argument("--body_part", default="chest")
    ap.add_argument("--n_samples", type=int, default=10)
    
    args = ap.parse_args()
    
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║  MIQA LOCAL TEST                                                     ║
║  CPU-only lightweight models                                         ║
╚══════════════════════════════════════════════════════════════════════╝
""")
    
    # Teste 1: Carregamento
    if not test_model_loading():
        print("❌ Nenhum modelo encontrado. Treine os modelos primeiro:")
        print("   python run_full_pipeline.py")
        return
    
    # Teste 2: Imagem única
    if args.image:
        test_prediction(args.image, args.modality, args.body_part)
    
    # Teste 3: Lote
    if args.dataset:
        test_batch_predictions(args.dataset, args.modality, args.body_part, args.n_samples)
    
    print("\n" + "=" * 70)
    print("✅ TESTES CONCLUÍDOS")
    print("=" * 70)


if __name__ == "__main__":
    main()
