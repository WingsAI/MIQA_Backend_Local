"""MIQA Training v2 — treinamento robusto com heavy augmentation.

Uso:
    python -m miqa.ml_models.train_v2 <<--modality rx <>> --body_part chest <>> --dataset_path ~/MIQA_datasets/rx/chest/covid_chest
"""
from __future__ import annotations
import argparse
import json
import pickle
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import cv2
from tqdm import tqdm

from miqa.ml_models.train_lightweight import extract_features, compute_teacher_score
from miqa.ml_models.augmentation import Augmenter


ROOT = Path(__file__).parent
CHECKPOINTS = ROOT / "checkpoints"


def train_v2(modality: str, body_part: str, dataset_path: Path,
             model_type: str = "rf", n_augmented: int = 5,
             max_images: int = 500, val_split: float = 0.2):
    """Treina modelo com heavy augmentation.
    
    Args:
        modality: rx, us, ct, mri
        body_part: chest, brain, liver, etc.
        dataset_path: diretório com imagens
        model_type: rf, xgb, ridge
        n_augmented: número de variantes augmentadas por imagem
        max_images: máximo de imagens originais
        val_split: fração para validação
    
    Returns:
        modelo treinado, metadata
    """
    print(f"\n{'='*70}")
    print(f"MIQA Training v2 — Heavy Augmentation")
    print(f"{'='*70}")
    print(f"Modalidade: {modality}")
    print(f"Body Part: {body_part}")
    print(f"Modelo: {model_type}")
    print(f"Dataset: {dataset_path}")
    print(f"Augmentações: {n_augmented} por imagem")
    print(f"Max imagens: {max_images}")
    print(f"{'='*70}\n")
    
    # Encontra imagens
    image_paths = []
    for ext in ["*.jpg", "*.jpeg", "*.png"]:
        image_paths.extend(dataset_path.rglob(ext))
    
    image_paths = sorted(image_paths)[:max_images]
    print(f"Encontradas {len(image_paths)} imagens originais")
    
    if len(image_paths) < 10:
        raise ValueError(f"Dataset muito pequeno: {len(image_paths)}")
    
    # Inicializa augmenter
    augmenter = Augmenter()
    all_samples = []
    
    print("\nExtraindo features com augmentation...")
    for i, img_path in enumerate(tqdm(image_paths)):
        # Carrega imagem original
        img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            continue
        if img.ndim == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Normaliza
        a, b = float(img.min()), float(img.max())
        img_norm = ((img - a) / max(b - a, 1e-9)).astype(np.float32)
        
        # Gera variantes augmentadas
        variants = augmenter.generate(img_norm, n_variants=n_augmented)
        
        for img_deg, deg_type, severity in variants:
            # Salva temporariamente para extrair features
            tmp_path = Path(f"/tmp/miqa_aug_{i}.png")
            cv2.imwrite(str(tmp_path), (img_deg * 255).astype(np.uint8))
            
            features = extract_features(tmp_path, modality)
            if features:
                # Score teacher ajustado pela degradação
                score = compute_teacher_score(features)
                
                # Penaliza score baseado na severidade da degradação
                if deg_type != 'original':
                    score = max(0, score - severity * 40)
                
                all_samples.append({
                    'features': features,
                    'score': score,
                    'deg_type': deg_type,
                    'severity': severity,
                    'source': img_path.name,
                })
    
    print(f"\nTotal de amostras: {len(all_samples)} ({len(image_paths)} originais)")
    
    # Prepara DataFrame
    df = pd.DataFrame([s['features'] for s in all_samples])
    df['score'] = [s['score'] for s in all_samples]
    df['deg_type'] = [s['deg_type'] for s in all_samples]
    df['severity'] = [s['severity'] for s in all_samples]
    
    # Preenche NaNs
    df = df.fillna(0)
    print(f"Amostras válidas: {len(df)}")
    
    # Estatísticas por tipo de degradação
    print("\nScore médio por tipo de degradação:")
    deg_stats = df.groupby('deg_type')['score'].agg(['count', 'mean', 'std']).round(2)
    print(deg_stats)
    
    # Split treino/validação (estratificado por deg_type)
    from sklearn.model_selection import train_test_split
    
    feature_cols = [c for c in df.columns if c not in ['score', 'deg_type', 'severity']]
    X = df[feature_cols]
    y = df['score']
    
    # Estratifica por deg_type para garantir representação
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=val_split, random_state=42, 
        stratify=df['deg_type']
    )
    
    print(f"\nTrain: {len(X_train)}, Val: {len(X_val)}")
    print(f"Features: {len(feature_cols)}")
    
    # Modelo
    print(f"\nTreinando {model_type}...")
    
    if model_type == "rf":
        from sklearn.ensemble import RandomForestRegressor
        model = RandomForestRegressor(
            n_estimators=200,        # Mais estimadores
            max_depth=15,            # Profundidade maior
            min_samples_split=3,     # Menor split
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
            bootstrap=True,
            oob_score=True,
        )
    elif model_type == "xgb":
        try:
            from xgboost import XGBRegressor
            model = XGBRegressor(
                n_estimators=200,
                max_depth=8,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=-1,
            )
        except ImportError:
            print("XGBoost não instalado, usando Random Forest")
            from sklearn.ensemble import RandomForestRegressor
            model = RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=-1)
    elif model_type == "ridge":
        from sklearn.linear_model import Ridge
        model = Ridge(alpha=1.0)
    else:
        from sklearn.ensemble import RandomForestRegressor
        model = RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=-1)
    
    model.fit(X_train, y_train)
    
    # Avaliação
    from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error
    
    train_pred = model.predict(X_train)
    val_pred = model.predict(X_val)
    
    metrics = {
        'train_mae': mean_absolute_error(y_train, train_pred),
        'val_mae': mean_absolute_error(y_val, val_pred),
        'train_r2': r2_score(y_train, train_pred),
        'val_r2': r2_score(y_val, val_pred),
        'train_rmse': np.sqrt(mean_squared_error(y_train, train_pred)),
        'val_rmse': np.sqrt(mean_squared_error(y_val, val_pred)),
    }
    
    print(f"\n{'='*70}")
    print("Resultados:")
    for k, v in metrics.items():
        print(f"  {k:12s}: {v:.4f}")
    print(f"{'='*70}")
    
    # Feature importance
    if hasattr(model, "feature_importances_"):
        importances = pd.Series(
            model.feature_importances_,
            index=feature_cols
        ).sort_values(ascending=False)
        print("\nTop 15 features:")
        for feat, imp in importances.head(15).items():
            print(f"  {feat:40s}: {imp:.4f}")
    
    # Salva modelo
    ckpt_dir = CHECKPOINTS / modality / body_part
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    
    model_path = ckpt_dir / f"{model_type}_v2_quality_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({
            "model": model,
            "feature_names": feature_cols,
            "model_type": model_type,
            "modality": modality,
            "body_part": body_part,
            **metrics,
            "n_train": len(X_train),
            "n_val": len(X_val),
            "n_features": len(feature_cols),
        }, f)
    
    print(f"\n💾 Modelo salvo: {model_path}")
    
    # Salva metadata completo
    meta = {
        "model_type": model_type,
        "modality": modality,
        "body_part": body_part,
        **{k: float(v) for k, v in metrics.items()},
        "n_samples": len(df),
        "n_features": len(feature_cols),
        "feature_names": feature_cols,
        "n_augmented": n_augmented,
        "degradation_stats": deg_stats.to_dict(),
    }
    
    meta_path = ckpt_dir / f"{model_type}_v2_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"📄 Metadata: {meta_path}")
    
    # Salva amostras para análise
    df.to_csv(ckpt_dir / "training_samples.csv", index=False)
    print(f"📊 Amostras: {ckpt_dir / 'training_samples.csv'}")
    
    return model, meta, df


def main():
    ap = argparse.ArgumentParser(description="MIQA Training v2 com heavy augmentation")
    ap.add_argument("--modality", required=True, choices=["rx", "us", "ct", "mri"])
    ap.add_argument("--body_part", required=True)
    ap.add_argument("--dataset_path", required=True, type=Path)
    ap.add_argument("--model_type", default="rf", choices=["rf", "xgb", "ridge"])
    ap.add_argument("--n_augmented", type=int, default=5)
    ap.add_argument("--max_images", type=int, default=500)
    
    args = ap.parse_args()
    
    model, meta, df = train_v2(
        modality=args.modality,
        body_part=args.body_part,
        dataset_path=args.dataset_path,
        model_type=args.model_type,
        n_augmented=args.n_augmented,
        max_images=args.max_images,
    )
    
    print("\n✅ Treinamento concluído!")
    print(f"Modelo: {meta['model_type']} v2")
    print(f"Val MAE: {meta['val_mae']:.2f}")
    print(f"Val R²: {meta['val_r2']:.3f}")


if __name__ == "__main__":
    main()
