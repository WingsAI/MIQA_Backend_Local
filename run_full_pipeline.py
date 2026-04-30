#!/usr/bin/env python3
"""Master script: treina modelos v2 com heavy augmentation + analisa todos os datasets.

Uso:
    python run_full_pipeline.py
"""
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Roda comando e mostra progresso."""
    print(f"\n{'='*70}")
    print(f"🚀 {description}")
    print(f"{'='*70}")
    print(f"Comando: {cmd}")
    print()
    
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"❌ Erro em: {description}")
        return False
    print(f"✅ {description} — OK")
    return True


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║  MIQA FULL PIPELINE — Training v2 + Analysis                        ║
║  Localhost testing with heavy augmentation                          ║
╚══════════════════════════════════════════════════════════════════════╝
""")
    
    datasets = [
        {
            "name": "RX Chest (COVID)",
            "modality": "rx",
            "body_part": "chest",
            "path": "~/MIQA_datasets/rx/chest/covid_chest/COVID-19_Radiography_Dataset",
            "max_images": 300,
        },
        {
            "name": "US Breast (BUSI)",
            "modality": "us",
            "body_part": "breast",
            "path": "~/MIQA_datasets/us/breast/busi/Dataset_BUSI_with_GT",
            "max_images": 500,
        },
        {
            "name": "CT Chest (COVID)",
            "modality": "ct",
            "body_part": "chest",
            "path": "~/MIQA_datasets/ct/chest/covid_ct",
            "max_images": 300,
        },
        {
            "name": "MRI Brain (Tumor)",
            "modality": "mri",
            "body_part": "brain",
            "path": "~/MIQA_datasets/mri/brain/brain_tumor",
            "max_images": 300,
        },
    ]
    
    # Passo 1: Treinar modelos v2
    print("📚 PASSO 1: TREINAMENTO V2 COM HEAVY AUGMENTATION")
    print("=" * 70)
    
    for ds in datasets:
        success = run_command(
            f"python3 -m miqa.ml_models.train_v2 "
            f"--modality {ds['modality']} "
            f"--body_part {ds['body_part']} "
            f"--dataset_path {ds['path']} "
            f"--model_type rf "
            f"--n_augmented 5 "
            f"--max_images {ds['max_images']}",
            f"Treinando {ds['name']}"
        )
        if not success:
            print(f"⚠️  Pulando análise de {ds['name']} devido a erro no treinamento")
            continue
        
        # Passo 2: Analisar dataset
        print(f"\n📊 PASSO 2: ANÁLISE DE {ds['name'].upper()}")
        print("=" * 70)
        
        run_command(
            f"python3 -m miqa.ml_models.analyze_datasets "
            f"--dataset_path {ds['path']} "
            f"--modality {ds['modality']} "
            f"--body_part {ds['body_part']} "
            f"--max_images 300",
            f"Analisando {ds['name']}"
        )
    
    # Passo 3: Atualizar dashboard
    print(f"\n🎨 PASSO 3: ATUALIZANDO DASHBOARD DE EXPERIMENTOS")
    print("=" * 70)
    
    run_command(
        "python3 -m miqa.ml_models.build_experiments_dashboard",
        "Atualizando dashboard"
    )
    
    # Resumo
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║  ✅ PIPELINE COMPLETO!                                               ║
╠══════════════════════════════════════════════════════════════════════╣
║  Arquivos gerados:                                                   ║
║    • Modelos: miqa/ml_models/checkpoints/*/*_v2_quality_model.pkl   ║
║    • Análises: analysis_results/*/*/*.png, *.json, *.csv            ║
║    • Dashboard: apresentacao_executivo/miqa-experiments.html        ║
╠══════════════════════════════════════════════════════════════════════╣
║  Próximo: Testar localmente com python test_local.py                ║
╚══════════════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
