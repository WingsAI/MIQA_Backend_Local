"""MIQA Lightweight ML — modelos de CPU para Image Quality Assessment.

REGRA: Nenhuma rede neural. Apenas modelos leves em CPU:
  - Random Forest
  - XGBoost (se disponível)
  - LightGBM (se disponível)
  - Fallback: Regressão Linear / Ridge

Estratégia:
  1. Extrai features físicas (nossas métricas)
  2. Teacher: score unificado das métricas
  3. Student: modelo leve que aprende features -> score
  4. Data augmentation: aplica degradações controladas

Uso:
    python -m miqa.ml_models.train_lightweight <<--modality rx <>> --body_part chest <>> --dataset_path ~/MIQA_datasets/rx/chest/covid_chest
"""
from __future__ import annotations
import argparse
import json
import pickle
import time
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import cv2

from miqa.anatomy import detect_anatomy, run_anatomy_aware_metrics
from miqa.metrics.universal_v2 import run_all_v2


# ========== CONFIG ==========
ROOT = Path(__file__).parent
CHECKPOINTS = ROOT / "checkpoints"


def extract_features(img_path: Path, modality: str) -> dict:
    """Extrai features físicas de uma imagem.
    
    Returns:
        dict com features numéricas
    """
    try:
        # Carrega imagem
        img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            return {}
        
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
        
        # Flatten para features
        features = {}
        
        # Features universais
        for name, data in universal.items():
            if isinstance(data, dict) and "value" in data:
                features[f"u_{name}"] = data["value"]
        
        # Features anatomy
        for name, data in anatomy.items():
            if isinstance(data, dict) and "value" in data:
                features[f"a_{name}"] = data["value"]
        
        # Features estatísticas básicas
        features["img_mean"] = float(img_norm.mean())
        features["img_std"] = float(img_norm.std())
        features["img_entropy"] = float(_compute_entropy(img_norm))
        
        return features
    except Exception as e:
        print(f"  Erro extraindo features de {img_path.name}: {e}")
        return {}


def _compute_entropy(img: np.ndarray) -> float:
    """Entropia de Shannon da imagem."""
    hist, _ = np.histogram(img, bins=256, range=(0, 1))
    hist = hist[hist > 0]
    p = hist / hist.sum()
    return float(-np.sum(p * np.log2(p)))


def compute_teacher_score(features: dict) -> float:
    """Computa score teacher a partir de features.
    
    Score de 0-100 baseado em heurísticas físicas.
    """
    scores = []
    
    # SNR/CNR (maior é melhor)
    for key in features:
        val = features[key]
        if np.isnan(val):
            continue
        if "snr" in key.lower() or "cnr" in key.lower():
            scores.append(min(val / 30, 1.0) * 100)
        elif "contrast" in key.lower():
            scores.append(min(val / 0.3, 1.0) * 100)
        elif "noise" in key.lower() or "mottle" in key.lower():
            scores.append(max(0, 1 - val / 50) * 100)
        elif "niqe" in key.lower():
            scores.append(max(0, 1 - val / 15) * 100)
        elif "brisque" in key.lower():
            scores.append(max(0, 1 - val / 80) * 100)
        elif "entropy" in key.lower():
            scores.append(min(val / 8, 1.0) * 100)
    
    if not scores:
        return 50.0
    
    return float(np.median(scores))


def apply_degradation(img: np.ndarray, deg_type: str, severity: float) -> np.ndarray:
    """Aplica degradação sintética para data augmentation.
    
    Args:
        img: imagem normalizada [0,1]
        deg_type: 'blur', 'noise', 'jpeg', 'contrast'
        severity: 0.0-1.0
    
    Returns:
        imagem degradada
    """
    img_8bit = (img * 255).astype(np.uint8)
    
    if deg_type == "blur":
        k = int(3 + severity * 10) // 2 * 2 + 1
        return cv2.GaussianBlur(img_8bit, (k, k), 0) / 255.0
    
    elif deg_type == "noise":
        noise = np.random.normal(0, severity * 0.1, img.shape)
        return np.clip(img + noise, 0, 1).astype(np.float32)
    
    elif deg_type == "jpeg":
        quality = int(95 - severity * 90)
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        _, enc = cv2.imencode(".jpg", img_8bit, encode_param)
        dec = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
        return dec.astype(np.float32) / 255.0
    
    elif deg_type == "contrast":
        alpha = 1.0 - severity * 0.5
        return np.clip((img - 0.5) * alpha + 0.5, 0, 1)
    
    return img


class DataAugmenter:
    """Gera variações degradadas de uma imagem para aumentar dataset."""
    
    DEG_TYPES = ["blur", "noise", "jpeg", "contrast"]
    SEVERITIES = [0.2, 0.4, 0.6, 0.8]
    
    def __init__(self, n_augments: int = 3):
        self.n_augments = n_augments
    
    def generate(self, img_path: Path, original_features: dict) -> list[dict]:
        """Gera exemplos augmentados.
        
        Returns:
            lista de dicts {'features': ..., 'score': ...}
        """
        samples = []
        
        # Original
        orig_score = compute_teacher_score(original_features)
        samples.append({"features": original_features, "score": orig_score})
        
        # Carrega imagem para degradações
        img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
        if img is None or img.ndim != 2:
            return samples
        
        a, b = float(img.min()), float(img.max())
        img_norm = ((img - a) / max(b - a, 1e-9)).astype(np.float32)
        
        # Gera degradações
        for _ in range(self.n_augments):
            deg_type = np.random.choice(self.DEG_TYPES)
            severity = np.random.choice(self.SEVERITIES)
            
            img_deg = apply_degradation(img_norm, deg_type, severity)
            
            # Salva temporariamente para re-extrair features
            tmp_path = Path("/tmp/miqa_aug.png")
            cv2.imwrite(str(tmp_path), (img_deg * 255).astype(np.uint8))
            
            # Extrai features da imagem degradada
            deg_features = extract_features(tmp_path, "rx")
            if deg_features:
                deg_score = compute_teacher_score(deg_features)
                # Score deve cair com degradação
                deg_score = max(0, deg_score - severity * 30)
                samples.append({"features": deg_features, "score": deg_score})
        
        return samples


def train_lightweight_model(modality: str, body_part: str, dataset_path: Path,
                            model_type: str = "rf", n_augments: int = 3,
                            max_images: int = 1000, val_split: float = 0.2):
    """Treina modelo leve em CPU.
    
    Args:
        modality: rx, us, ct, mri
        body_part: chest, brain, liver, etc.
        dataset_path: diretório com imagens
        model_type: 'rf' (Random Forest), 'xgb', 'lgb', 'ridge'
        n_augments: número de augmentações por imagem
        max_images: máximo de imagens
        val_split: fração para validação
    
    Returns:
        modelo treinado, métricas
    """
    print(f"\n{'='*60}")
    print(f"MIQA Lightweight Training")
    print(f"{'='*60}")
    print(f"Modalidade: {modality}")
    print(f"Body Part: {body_part}")
    print(f"Modelo: {model_type}")
    print(f"Dataset: {dataset_path}")
    print(f"Augmentações: {n_augments}")
    print(f"Max imagens: {max_images}")
    print(f"{'='*60}\n")
    
    # Encontra imagens
    image_paths = []
    for ext in ["*.jpg", "*.jpeg", "*.png"]:
        image_paths.extend(dataset_path.rglob(ext))
    
    image_paths = sorted(image_paths)[:max_images]
    print(f"Encontradas {len(image_paths)} imagens")
    
    if len(image_paths) < 10:
        raise ValueError(f"Dataset muito pequeno: {len(image_paths)} imagens")
    
    # Extrai features e scores
    augmenter = DataAugmenter(n_augments=n_augments)
    all_samples = []
    
    print("\nExtraindo features...")
    for i, img_path in enumerate(image_paths):
        if i % 50 == 0:
            print(f"  {i}/{len(image_paths)}")
        
        features = extract_features(img_path, modality)
        if not features:
            continue
        
        # Gera augmentações
        samples = augmenter.generate(img_path, features)
        all_samples.extend(samples)
    
    print(f"\nTotal de amostras: {len(all_samples)} (original: {len(image_paths)})")
    
    # Prepara DataFrame
    df = pd.DataFrame([s["features"] for s in all_samples])
    df["score"] = [s["score"] for s in all_samples]
    
    # Preenche NaNs com 0 (features ausentes = 0)
    df = df.fillna(0)
    print(f"Amostras válidas: {len(df)}")
    print(f"Features: {list(df.columns)}")
    
    if len(df) < 20:
        raise ValueError(f"Dados insuficientes após limpeza: {len(df)}")
    
    # Estatísticas
    print(f"\nScore teacher — média: {df['score'].mean():.1f}, "
          f"std: {df['score'].std():.1f}, "
          f"min: {df['score'].min():.1f}, max: {df['score'].max():.1f}")
    
    # Split
    from sklearn.model_selection import train_test_split
    X = df.drop("score", axis=1)
    y = df["score"]
    
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=val_split, random_state=42
    )
    
    print(f"\nTrain: {len(X_train)}, Val: {len(X_val)}")
    print(f"Features: {list(X.columns)}")
    
    # Modelo
    print(f"\nTreinando {model_type}...")
    
    if model_type == "rf":
        from sklearn.ensemble import RandomForestRegressor
        model = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            random_state=42,
            n_jobs=-1
        )
    elif model_type == "xgb":
        try:
            from xgboost import XGBRegressor
            model = XGBRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=42,
                n_jobs=-1
            )
        except ImportError:
            print("XGBoost não instalado, usando Random Forest")
            from sklearn.ensemble import RandomForestRegressor
            model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
    elif model_type == "ridge":
        from sklearn.linear_model import Ridge
        model = Ridge(alpha=1.0)
    else:
        from sklearn.ensemble import RandomForestRegressor
        model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
    
    model.fit(X_train, y_train)
    
    # Avaliação
    train_pred = model.predict(X_train)
    val_pred = model.predict(X_val)
    
    from sklearn.metrics import mean_absolute_error, r2_score
    
    train_mae = mean_absolute_error(y_train, train_pred)
    val_mae = mean_absolute_error(y_val, val_pred)
    train_r2 = r2_score(y_train, train_pred)
    val_r2 = r2_score(y_val, val_pred)
    
    print(f"\n{'='*60}")
    print("Resultados:")
    print(f"  Train MAE: {train_mae:.2f}")
    print(f"  Val MAE:   {val_mae:.2f}")
    print(f"  Train R²:  {train_r2:.3f}")
    print(f"  Val R²:    {val_r2:.3f}")
    print(f"{'='*60}")
    
    # Feature importance
    if hasattr(model, "feature_importances_"):
        importances = pd.Series(
            model.feature_importances_,
            index=X.columns
        ).sort_values(ascending=False)
        print("\nTop 10 features:")
        for feat, imp in importances.head(10).items():
            print(f"  {feat}: {imp:.3f}")
    
    # Salva modelo
    ckpt_dir = CHECKPOINTS / modality / body_part
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    
    model_path = ckpt_dir / f"{model_type}_quality_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({
            "model": model,
            "feature_names": list(X.columns),
            "model_type": model_type,
            "modality": modality,
            "body_part": body_part,
            "val_mae": val_mae,
            "val_r2": val_r2,
            "n_samples": len(df),
            "n_features": len(X.columns),
        }, f)
    
    print(f"\n💾 Modelo salvo: {model_path}")
    
    # Salva metadata
    meta = {
        "model_type": model_type,
        "modality": modality,
        "body_part": body_part,
        "val_mae": float(val_mae),
        "val_r2": float(val_r2),
        "train_mae": float(train_mae),
        "train_r2": float(train_r2),
        "n_samples": len(df),
        "n_features": len(X.columns),
        "feature_names": list(X.columns),
        "n_augments": n_augments,
    }
    
    meta_path = ckpt_dir / f"{model_type}_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"📄 Metadata: {meta_path}")
    
    return model, meta


def load_model(modality: str, body_part: str, model_type: str = "rf"):
    """Carrega modelo treinado.
    
    Args:
        modality: rx, us, ct, mri
        body_part: chest, brain, liver, etc.
        model_type: rf, xgb, ridge
    
    Returns:
        dict com 'model' e 'feature_names' ou None
    """
    model_path = CHECKPOINTS / modality / body_part / f"{model_type}_quality_model.pkl"
    
    if not model_path.exists():
        return None
    
    with open(model_path, "rb") as f:
        data = pickle.load(f)
    
    return data


def predict_quality(img_path: Path, modality: str, body_part: str,
                    model_type: str = "rf") -> Optional[float]:
    """Prediz score de qualidade para uma imagem.
    
    Args:
        img_path: caminho da imagem
        modality: rx, us, ct, mri
        body_part: chest, brain, liver, etc.
        model_type: rf, xgb, ridge
    
    Returns:
        score [0, 100] ou None
    """
    # Carrega modelo
    data = load_model(modality, body_part, model_type)
    if data is None:
        return None
    
    model = data["model"]
    feature_names = data["feature_names"]
    
    # Extrai features
    features = extract_features(img_path, modality)
    if not features:
        return None
    
    # Prepara input
    X = pd.DataFrame([features])
    
    # Garante colunas corretas
    for col in feature_names:
        if col not in X.columns:
            X[col] = 0.0
    X = X[feature_names]
    
    # Prediz
    score = model.predict(X)[0]
    return float(np.clip(score, 0, 100))


def main():
    ap = argparse.ArgumentParser(description="Treina modelo MIQA leve em CPU")
    ap.add_argument("--modality", required=True, choices=["rx", "us", "ct", "mri"])
    ap.add_argument("--body_part", required=True)
    ap.add_argument("--dataset_path", required=True, type=Path)
    ap.add_argument("--model_type", default="rf", choices=["rf", "xgb", "ridge"])
    ap.add_argument("--n_augments", type=int, default=3)
    ap.add_argument("--max_images", type=int, default=1000)
    
    args = ap.parse_args()
    
    model, meta = train_lightweight_model(
        modality=args.modality,
        body_part=args.body_part,
        dataset_path=args.dataset_path,
        model_type=args.model_type,
        n_augments=args.n_augments,
        max_images=args.max_images,
    )
    
    print("\n✅ Treinamento concluído!")
    print(f"Modelo: {meta['model_type']}")
    print(f"Val MAE: {meta['val_mae']:.2f}")
    print(f"Val R²: {meta['val_r2']:.3f}")


if __name__ == "__main__":
    main()
