"""MIQA Analysis Pipeline — análise completa dos datasets e modelos.

Gera:
1. Estatísticas descritivas (scores, distribuições, outliers)
2. Visualizações (histogramas, exemplos bons/ruins)
3. Correlação entre métricas e classes do dataset
4. Validação em imagens reais

Uso:
    python -m miqa.ml_models.analyze_datasets --dataset_path ~/MIQA_datasets/rx/chest/covid_chest --modality rx --body_part chest
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import cv2
from tqdm import tqdm

from miqa.ml_models.train_lightweight import extract_features, compute_teacher_score


# Configurações de plot
plt.rcParams.update({
    "figure.figsize": (12, 8),
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 13,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
})


def analyze_dataset(dataset_path: Path, modality: str, body_part: str, 
                    max_images: int = 500) -> pd.DataFrame:
    """Analisa dataset completo: extrai features e scores.
    
    Returns:
        DataFrame com features e scores de todas as imagens
    """
    print(f"\nAnalisando dataset: {dataset_path}")
    print(f"Modalidade: {modality}, Body Part: {body_part}")
    
    # Encontra imagens
    image_paths = []
    for ext in ["*.jpg", "*.jpeg", "*.png"]:
        image_paths.extend(dataset_path.rglob(ext))
    
    image_paths = sorted(image_paths)[:max_images]
    print(f"Total de imagens: {len(image_paths)}")
    
    # Extrai features
    samples = []
    for img_path in tqdm(image_paths, desc="Extraindo features"):
        features = extract_features(img_path, modality)
        if features:
            score = compute_teacher_score(features)
            
            # Detecta classe se possível (diretório pai)
            class_name = detect_class_from_path(img_path)
            
            samples.append({
                'path': str(img_path),
                'filename': img_path.name,
                'class': class_name,
                'score': score,
                **features,
            })
    
    df = pd.DataFrame(samples)
    print(f"Amostras válidas: {len(df)}")
    
    return df


def detect_class_from_path(img_path: Path) -> str:
    """Detecta classe da imagem baseado na estrutura de diretórios."""
    # Tenta pegar o nome do diretório pai
    parent = img_path.parent.name.lower()
    
    # Limpa nomes comuns
    classes = ['covid', 'normal', 'pneumonia', 'benign', 'malignant', 
               'glioma', 'meningioma', 'pituitary', 'no_tumor']
    
    for cls in classes:
        if cls in parent or cls in img_path.name.lower():
            return cls
    
    return parent


def generate_statistics(df: pd.DataFrame, output_dir: Path):
    """Gera estatísticas descritivas."""
    print("\n" + "="*70)
    print("1. ESTATÍSTICAS DESCRITIVAS")
    print("="*70)
    
    stats = {
        'n_samples': len(df),
        'score_mean': df['score'].mean(),
        'score_std': df['score'].std(),
        'score_min': df['score'].min(),
        'score_max': df['score'].max(),
        'score_median': df['score'].median(),
        'score_q25': df['score'].quantile(0.25),
        'score_q75': df['score'].quantile(0.75),
        'score_iqr': df['score'].quantile(0.75) - df['score'].quantile(0.25),
    }
    
    # Outliers (score < Q1 - 1.5*IQR ou > Q3 + 1.5*IQR)
    q1, q3 = stats['score_q25'], stats['score_q75']
    iqr = stats['score_iqr']
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    
    outliers_low = df[df['score'] < lower_bound]
    outliers_high = df[df['score'] > upper_bound]
    
    stats['n_outliers_low'] = len(outliers_low)
    stats['n_outliers_high'] = len(outliers_high)
    stats['pct_outliers'] = (len(outliers_low) + len(outliers_high)) / len(df) * 100
    
    print(f"\nScore de Qualidade:")
    print(f"  Média:    {stats['score_mean']:.2f}")
    print(f"  Mediana:  {stats['score_median']:.2f}")
    print(f"  Std:      {stats['score_std']:.2f}")
    print(f"  Min:      {stats['score_min']:.2f}")
    print(f"  Max:      {stats['score_max']:.2f}")
    print(f"  Q1/Q3:    {stats['score_q25']:.2f} / {stats['score_q75']:.2f}")
    print(f"\nOutliers:")
    print(f"  Baixos:   {stats['n_outliers_low']} ({len(outliers_low)/len(df)*100:.1f}%)")
    print(f"  Altos:    {stats['n_outliers_high']} ({len(outliers_high)/len(df)*100:.1f}%)")
    
    # Salva estatísticas
    stats_path = output_dir / "statistics.json"
    stats_path.write_text(json.dumps({k: float(v) if isinstance(v, (np.floating, float)) else int(v) if isinstance(v, (np.integer, int)) else v for k, v in stats.items()}, indent=2))
    print(f"\n📊 Estatísticas salvas: {stats_path}")
    
    return stats, outliers_low, outliers_high


def generate_visualizations(df: pd.DataFrame, output_dir: Path):
    """Gera visualizações: histogramas, boxplots, exemplos."""
    print("\n" + "="*70)
    print("2. VISUALIZAÇÕES")
    print("="*70)
    
    # 1. Histograma de scores
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # Histograma
    axes[0, 0].hist(df['score'], bins=50, color='steelblue', edgecolor='black', alpha=0.7)
    axes[0, 0].axvline(df['score'].mean(), color='red', linestyle='--', label=f'Média: {df["score"].mean():.1f}')
    axes[0, 0].axvline(df['score'].median(), color='green', linestyle='--', label=f'Mediana: {df["score"].median():.1f}')
    axes[0, 0].set_xlabel('Score de Qualidade')
    axes[0, 0].set_ylabel('Frequência')
    axes[0, 0].set_title('Distribuição de Scores')
    axes[0, 0].legend()
    axes[0, 0].grid(alpha=0.3)
    
    # Boxplot por classe
    if 'class' in df.columns and df['class'].nunique() > 1:
        df.boxplot(column='score', by='class', ax=axes[0, 1])
        axes[0, 1].set_title('Score por Classe')
        axes[0, 1].set_xlabel('Classe')
        axes[0, 1].set_ylabel('Score')
        plt.suptitle('')  # Remove título automático
    else:
        axes[0, 1].text(0.5, 0.5, 'Classes não detectadas', ha='center', va='center')
        axes[0, 1].set_title('Score por Classe')
    
    # QQ-plot (normalidade)
    from scipy import stats
    stats.probplot(df['score'], dist="norm", plot=axes[1, 0])
    axes[1, 0].set_title('Q-Q Plot (Normalidade)')
    axes[1, 0].grid(alpha=0.3)
    
    # Violin plot
    axes[1, 1].violinplot([df['score']], positions=[1], showmeans=True, showmedians=True)
    axes[1, 1].set_xticks([1])
    axes[1, 1].set_xticklabels(['Todos'])
    axes[1, 1].set_ylabel('Score')
    axes[1, 1].set_title('Distribuição (Violin Plot)')
    axes[1, 1].grid(alpha=0.3)
    
    plt.tight_layout()
    viz_path = output_dir / "score_distributions.png"
    plt.savefig(viz_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"📊 Distribuições: {viz_path}")
    
    # 2. Exemplos bons e ruins
    n_examples = min(6, len(df) // 2)
    best = df.nlargest(n_examples, 'score')
    worst = df.nsmallest(n_examples, 'score')
    
    fig, axes = plt.subplots(2, n_examples, figsize=(n_examples*3, 6))
    
    # Melhores
    for i, (_, row) in enumerate(best.iterrows()):
        img = cv2.imread(row['path'], cv2.IMREAD_GRAYSCALE)
        if img is not None:
            axes[0, i].imshow(img, cmap='gray')
            axes[0, i].set_title(f'Score: {row["score"]:.1f}\n{row["class"]}', fontsize=9)
            axes[0, i].axis('off')
    axes[0, 0].set_ylabel('MELHORES', fontsize=11, fontweight='bold', rotation=0, ha='right')
    
    # Piores
    for i, (_, row) in enumerate(worst.iterrows()):
        img = cv2.imread(row['path'], cv2.IMREAD_GRAYSCALE)
        if img is not None:
            axes[1, i].imshow(img, cmap='gray')
            axes[1, i].set_title(f'Score: {row["score"]:.1f}\n{row["class"]}', fontsize=9)
            axes[1, i].axis('off')
    axes[1, 0].set_ylabel('PIORES', fontsize=11, fontweight='bold', rotation=0, ha='right')
    
    plt.suptitle('Exemplos de Qualidade', fontsize=14, fontweight='bold')
    plt.tight_layout()
    examples_path = output_dir / "quality_examples.png"
    plt.savefig(examples_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"📷 Exemplos: {examples_path}")


def generate_correlation_analysis(df: pd.DataFrame, output_dir: Path):
    """Analisa correlação entre métricas e classes."""
    print("\n" + "="*70)
    print("3. CORRELAÇÃO MÉTRICAS × CLASSES")
    print("="*70)
    
    if 'class' not in df.columns or df['class'].nunique() <= 1:
        print("⚠️  Classes não detectadas. Pulando análise de correlação.")
        return
    
    # Estatísticas por classe
    class_stats = df.groupby('class')['score'].agg(['count', 'mean', 'std', 'min', 'max']).round(2)
    print("\nScore por classe:")
    print(class_stats)
    
    # Teste ANOVA
    from scipy import stats
    classes = df['class'].unique()
    groups = [df[df['class'] == cls]['score'].values for cls in classes]
    
    if len(groups) >= 2 and all(len(g) > 1 for g in groups):
        f_stat, p_value = stats.f_oneway(*groups)
        print(f"\nANOVA:")
        print(f"  F-statistic: {f_stat:.4f}")
        print(f"  p-value:     {p_value:.6f}")
        print(f"  Significativo: {'Sim' if p_value < 0.05 else 'Não'}")
    
    # Correlação entre features e classe
    # Codifica classes numericamente
    class_codes = pd.Categorical(df['class']).codes
    
    feature_cols = [c for c in df.columns if c not in ['path', 'filename', 'class', 'score']]
    correlations = []
    
    for feat in feature_cols:
        corr = np.corrcoef(df[feat], class_codes)[0, 1]
        correlations.append((feat, abs(corr), corr))
    
    correlations.sort(key=lambda x: x[1], reverse=True)
    
    print("\nTop 10 features correlacionadas com classe:")
    for feat, abs_corr, corr in correlations[:10]:
        print(f"  {feat:40s}: {corr:7.3f}")
    
    # Salva
    corr_data = {
        'class_stats': class_stats.to_dict(),
        'anova_f': float(f_stat) if len(groups) >= 2 else None,
        'anova_p': float(p_value) if len(groups) >= 2 else None,
        'feature_correlations': {feat: float(corr) for feat, _, corr in correlations[:20]},
    }
    
    corr_path = output_dir / "correlation_analysis.json"
    corr_path.write_text(json.dumps(corr_data, indent=2))
    print(f"\n📊 Correlações salvas: {corr_path}")
    
    # Visualização
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Boxplot
    df.boxplot(column='score', by='class', ax=axes[0])
    axes[0].set_title('Score de Qualidade por Classe')
    axes[0].set_xlabel('Classe')
    axes[0].set_ylabel('Score')
    plt.suptitle('')
    
    # Barras média
    means = df.groupby('class')['score'].mean().sort_values(ascending=False)
    axes[1].bar(range(len(means)), means.values, color='steelblue')
    axes[1].set_xticks(range(len(means)))
    axes[1].set_xticklabels(means.index, rotation=45, ha='right')
    axes[1].set_ylabel('Score Médio')
    axes[1].set_title('Score Médio por Classe')
    axes[1].grid(alpha=0.3, axis='y')
    
    plt.tight_layout()
    corr_viz_path = output_dir / "correlation_plot.png"
    plt.savefig(corr_viz_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"📊 Gráfico correlação: {corr_viz_path}")


def validate_on_real_images(df: pd.DataFrame, output_dir: Path, n_samples: int = 50):
    """Valida predições em amostra real."""
    print("\n" + "="*70)
    print("4. VALIDAÇÃO EM IMAGENS REAIS")
    print("="*70)
    
    # Carrega modelo se disponível
    from miqa.ml_models import predict_quality, list_available_models
    
    models = list_available_models()
    
    if not models:
        print("⚠️  Nenhum modelo treinado encontrado. Treine um modelo primeiro.")
        return
    
    # Pega amostra aleatória
    sample = df.sample(min(n_samples, len(df)), random_state=42)
    
    predictions = []
    errors = []
    
    print(f"\nValidando {len(sample)} imagens...")
    
    for _, row in tqdm(sample.iterrows(), total=len(sample)):
        img_path = Path(row['path'])
        
        # Predição do modelo
        try:
            # Tenta detectar modality/body_part do path
            modality = 'rx' if 'rx' in str(img_path).lower() else 'us' if 'us' in str(img_path).lower() else 'ct' if 'ct' in str(img_path).lower() else 'mri'
            body_part = 'chest' if 'chest' in str(img_path).lower() or 'covid' in str(img_path).lower() else 'brain' if 'brain' in str(img_path).lower() else 'breast' if 'busi' in str(img_path).lower() else 'chest'
            
            pred_score = predict_quality(img_path, modality=modality, body_part=body_part)
            
            if pred_score is not None:
                true_score = row['score']
                error = abs(pred_score - true_score)
                
                predictions.append({
                    'true': true_score,
                    'predicted': pred_score,
                    'error': error,
                    'path': str(img_path),
                })
        except Exception as e:
            pass
    
    if not predictions:
        print("⚠️  Não foi possível fazer predições. Verifique se os modelos estão treinados.")
        return
    
    pred_df = pd.DataFrame(predictions)
    
    mae = pred_df['error'].mean()
    rmse = np.sqrt((pred_df['error'] ** 2).mean())
    
    print(f"\nResultados da Validação ({len(pred_df)} amostras):")
    print(f"  MAE:  {mae:.2f}")
    print(f"  RMSE: {rmse:.2f}")
    print(f"  Erro máx: {pred_df['error'].max():.2f}")
    
    # Visualização
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # Scatter plot
    axes[0].scatter(pred_df['true'], pred_df['predicted'], alpha=0.6, color='steelblue')
    axes[0].plot([0, 100], [0, 100], 'r--', label='Perfeito')
    axes[0].set_xlabel('Score Real (Teacher)')
    axes[0].set_ylabel('Score Predito (Modelo)')
    axes[0].set_title(f'Validação: True vs Predicted\nMAE={mae:.2f}')
    axes[0].legend()
    axes[0].grid(alpha=0.3)
    
    # Histograma de erros
    axes[1].hist(pred_df['error'], bins=20, color='coral', edgecolor='black', alpha=0.7)
    axes[1].axvline(mae, color='red', linestyle='--', label=f'MAE: {mae:.2f}')
    axes[1].set_xlabel('Erro Absoluto')
    axes[1].set_ylabel('Frequência')
    axes[1].set_title('Distribuição dos Erros')
    axes[1].legend()
    axes[1].grid(alpha=0.3)
    
    plt.tight_layout()
    val_path = output_dir / "validation_results.png"
    plt.savefig(val_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"📊 Validação: {val_path}")


def main():
    ap = argparse.ArgumentParser(description="Análise completa de datasets MIQA")
    ap.add_argument("--dataset_path", required=True, type=Path)
    ap.add_argument("--modality", required=True, choices=["rx", "us", "ct", "mri"])
    ap.add_argument("--body_part", required=True)
    ap.add_argument("--max_images", type=int, default=500)
    ap.add_argument("--output_dir", type=Path, default=None)
    
    args = ap.parse_args()
    
    # Diretório de saída
    if args.output_dir is None:
        args.output_dir = Path("analysis_results") / args.modality / args.body_part
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*70}")
    print("MIQA DATASET ANALYSIS")
    print(f"{'='*70}")
    print(f"Dataset: {args.dataset_path}")
    print(f"Output:  {args.output_dir}")
    
    # 1. Analisa dataset
    df = analyze_dataset(args.dataset_path, args.modality, args.body_part, args.max_images)
    
    if len(df) == 0:
        print("❌ Nenhuma imagem válida encontrada.")
        return
    
    # 2. Estatísticas
    stats, outliers_low, outliers_high = generate_statistics(df, args.output_dir)
    
    # 3. Visualizações
    generate_visualizations(df, args.output_dir)
    
    # 4. Correlação
    generate_correlation_analysis(df, args.output_dir)
    
    # 5. Validação
    validate_on_real_images(df, args.output_dir)
    
    # Salva DataFrame completo
    df.to_csv(args.output_dir / "analysis_data.csv", index=False)
    
    print("\n" + "="*70)
    print("✅ ANÁLISE COMPLETA!")
    print(f"Resultados em: {args.output_dir}")
    print(f"Arquivos gerados:")
    for f in sorted(args.output_dir.iterdir()):
        print(f"  • {f.name}")
    print("="*70)


if __name__ == "__main__":
    main()
