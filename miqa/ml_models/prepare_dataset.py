"""Script para preparar datasets Kaggle para treinamento MIQA.

Uso:
    python -m miqa.ml_models.prepare_dataset --dataset covid_chest --output_dir ./data/covid_chest
"""
from __future__ import annotations
import argparse
import shutil
from pathlib import Path
from typing import Optional

import pandas as pd


# Configurações de datasets Kaggle recomendados
DATASET_CONFIGS = {
    # RX
    "covid_chest": {
        "modality": "rx",
        "body_part": "chest",
        "kaggle_id": "tawsifurrahman/covid19-radiography-database",
        "description": "COVID-19 Radiography Database (21k imagens)",
        "classes": ["COVID", "Lung_Opacity", "Normal", "Viral Pneumonia"],
    },
    "nih_chest": {
        "modality": "rx",
        "body_part": "chest", 
        "kaggle_id": "nih-chest-xrays/data",
        "description": "NIH Chest X-ray 14 (112k imagens)",
        "classes": None,  # Multi-label
    },
    "mura": {
        "modality": "rx",
        "body_part": "extremity",
        "kaggle_id": "microsoft/mura",
        "description": "MURA - MUsculo-skeletal RAdiographs (40k)",
        "classes": ["normal", "abnormal"],
    },
    # US
    "busi": {
        "modality": "us",
        "body_part": "breast",
        "kaggle_id": "aryashah2k/breast-ultrasound-images-dataset",
        "description": "Breast Ultrasound Images (780 imagens)",
        "classes": ["benign", "malignant", "normal"],
    },
    # CT
    "covid_ct": {
        "modality": "ct",
        "body_part": "chest",
        "kaggle_id": "plameneduardo/sars-cov-2-ct-scan-dataset",
        "description": "COVID-19 CT Scans",
        "classes": ["COVID", "non-COVID"],
    },
    # MRI
    "brain_tumor_mri": {
        "modality": "mri",
        "body_part": "brain",
        "kaggle_id": "sartajbhuvaji/brain-tumor-classification-mri",
        "description": "Brain Tumor MRI (3k imagens)",
        "classes": ["glioma", "meningioma", "pituitary", "no_tumor"],
    },
    "knee_mri": {
        "modality": "mri",
        "body_part": "knee",
        "kaggle_id": "omarlouiselli/multiclass-knee-mri-dataset",
        "description": "Multiclass Knee MRI",
        "classes": ["normal", "abnormal"],
    },
}


def print_dataset_info():
    """Imprime informações sobre datasets disponíveis."""
    print("=" * 80)
    print("DATASETS KAGGLE RECOMENDADOS PARA MIQA")
    print("=" * 80)
    
    for name, config in DATASET_CONFIGS.items():
        print(f"\n📊 {name}")
        print(f"   Modalidade: {config['modality'].upper()}")
        print(f"   Parte: {config['body_part']}")
        print(f"   Kaggle: {config['kaggle_id']}")
        print(f"   Descrição: {config['description']}")
        if config['classes']:
            print(f"   Classes: {', '.join(config['classes'])}")
        print(f"   Download: kaggle datasets download -d {config['kaggle_id']}")
    
    print("\n" + "=" * 80)


def setup_dataset_structure(dataset_name: str, raw_dir: Path, output_dir: Path):
    """Organiza imagens em estrutura padronizada para treinamento.
    
    Args:
        dataset_name: nome do dataset (covid_chest, busi, etc.)
        raw_dir: diretório com dados brutos baixados do Kaggle
        output_dir: diretório de saída organizado
    """
    config = DATASET_CONFIGS.get(dataset_name)
    if not config:
        raise ValueError(f"Dataset desconhecido: {dataset_name}")
    
    modality = config["modality"]
    body_part = config["body_part"]
    
    # Cria estrutura
    out_path = output_dir / modality / body_part / dataset_name
    out_path.mkdir(parents=True, exist_ok=True)
    
    print(f"Organizando {dataset_name}...")
    print(f"  De: {raw_dir}")
    print(f"  Para: {out_path}")
    
    # Conta imagens
    image_count = 0
    for ext in ["*.jpg", "*.jpeg", "*.png", "*.dcm"]:
        for img_path in raw_dir.rglob(ext):
            if img_path.stat().st_size > 1024:  # Ignora arquivos vazios
                # Cria link simbólico ou copia
                dest = out_path / img_path.name
                if not dest.exists():
                    shutil.copy2(img_path, dest)
                image_count += 1
    
    print(f"  {image_count} imagens organizadas")
    
    # Cria metadata
    import json
    metadata = {
        "dataset_name": dataset_name,
        "modality": modality,
        "body_part": body_part,
        "kaggle_id": config["kaggle_id"],
        "n_images": image_count,
        "classes": config["classes"],
    }
    
    meta_file = out_path / "metadata.json"
    meta_file.write_text(json.dumps(metadata, indent=2))
    
    print(f"  Metadata: {meta_file}")
    
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Prepara datasets Kaggle para MIQA")
    ap.add_argument("--list", action="store_true", help="Lista datasets disponíveis")
    ap.add_argument("--dataset", help="Nome do dataset a preparar")
    ap.add_argument("--raw_dir", type=Path, help="Diretório com dados brutos")
    ap.add_argument("--output_dir", type=Path, default=Path("./data/kaggle"),
                    help="Diretório de saída")
    
    args = ap.parse_args()
    
    if args.list or not args.dataset:
        print_dataset_info()
        return
    
    if not args.raw_dir:
        print("Erro: --raw_dir obrigatório quando --dataset é especificado")
        return
    
    setup_dataset_structure(args.dataset, args.raw_dir, args.output_dir)
    print("\n✅ Dataset preparado!")
    print(f"\nPara treinar:")
    config = DATASET_CONFIGS[args.dataset]
    print(f"  python -m miqa.ml_models.train <>\u003e <<<<")
    print(f"    --modality {config['modality']} <>> <<<<")
    print(f"    --body_part {config['body_part']} <>> <<<<")
    print(f"    --dataset_path {args.output_dir / config['modality'] / config['body_part'] / args.dataset}")


if __name__ == "__main__":
    main()
