#!/usr/bin/env python3
"""
MIQA Auto-Research Pipeline

Melhoria contínua de métricas e modelos via:
1. Análise de feature importance
2. Identificação de métricas redundantes
3. Sugestão de novas métricas baseadas em literatura
4. Otimização de hiperparâmetros
5. Validação cruzada adversarial

Uso:
    python auto_research.py --mode analyze
    python auto_research.py --mode suggest_metrics
    python auto_research.py --mode optimize
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_score, GridSearchCV
from sklearn.metrics import mean_absolute_error, r2_score
import cv2
from tqdm import tqdm

class MIQAAutoResearch:
    """Pipeline de auto-research para MIQA."""
    
    def __init__(self, checkpoints_dir="miqa/ml_models/checkpoints"):
        self.checkpoints_dir = Path(checkpoints_dir)
        self.results = {}
        
    def analyze_all_models(self):
        """Analisa todos os modelos treinados."""
        print("=" * 70)
        print("MIQA Auto-Research — Análise de Modelos")
        print("=" * 70)
        
        for metadata_file in self.checkpoints_dir.rglob("*metadata.json"):
            with open(metadata_file) as f:
                meta = json.load(f)
            
            model_name = metadata_file.parent.name
            modality = meta.get('modality', 'unknown')
            body_part = meta.get('body_part', 'unknown')
            
            print(f"\n📊 {modality}/{body_part}")
            print(f"   MAE: {meta.get('val_mae', 'N/A'):.3f}")
            print(f"   R²:  {meta.get('val_r2', 'N/A'):.3f}")
            print(f"   Amostras: {meta.get('n_samples', 'N/A')}")
            
            # Análise de feature importance
            if 'feature_importance' in str(metadata_file.parent):
                self._analyze_feature_importance(metadata_file.parent)
                
    def _analyze_feature_importance(self, model_dir):
        """Analisa importância das features."""
        # Carrega modelo
        model_file = model_dir / "rf_v2_quality_model.pkl"
        if not model_file.exists():
            model_file = model_dir / "rf_quality_model.pkl"
        
        if not model_file.exists():
            return
            
        import joblib
        model = joblib.load(model_file)
        
        # Carrega metadata para nomes das features
        meta_file = model_dir / "rf_v2_metadata.json"
        if not meta_file.exists():
            meta_file = model_dir / "rf_metadata.json"
        
        with open(meta_file) as f:
            meta = json.load(f)
        
        feature_names = meta.get('feature_names', [f'f{i}' for i in range(len(model.feature_importances_))])
        
        # Cria DataFrame de importância
        importance_df = pd.DataFrame({
            'feature': feature_names,
            'importance': model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        print(f"\n   Top Features:")
        for _, row in importance_df.head(5).iterrows():
            print(f"      {row['feature']:40s}: {row['importance']:.4f}")
        
        # Identifica features redundantes (importância < 1%)
        redundant = importance_df[importance_df['importance'] < 0.01]['feature'].tolist()
        if redundant:
            print(f"\n   ⚠️  Features redundantes (< 1%): {', '.join(redundant)}")
            
        return importance_df
    
    def suggest_new_metrics(self, modality):
        """Sugere novas métricas baseadas na literatura."""
        print(f"\n{'='*70}")
        print(f"Sugestões de Métricas para {modality.upper()}")
        print(f"{'='*70}")
        
        suggestions = {
            'rx': [
                {
                    'name': 'clavicle_symmetry',
                    'description': 'Simetria da clavícula (indica rotação)',
                    'rationale': 'RX rotacionado reduz visibilidade de patologias',
                    'implementation': 'Detecção de bordas + correlação E/D',
                    'priority': 'high'
                },
                {
                    'name': 'rib_count_visibility',
                    'description': 'Número de costelas visíveis acima do diafragma',
                    'rationale': 'Indica profundidade de inspiração (PAD)',
                    'implementation': 'Detecção de bordas horizontais + contagem',
                    'priority': 'high'
                },
                {
                    'name': 'cardiothoracic_ratio',
                    'description': 'Razão cardiotorácica',
                    'rationale': 'Cardiomegalia afeta qualidade técnica do RX',
                    'implementation': 'Segmentação do coração / largura do tórax',
                    'priority': 'medium'
                },
                {
                    'name': 'costophrenic_angle_sharpness',
                    'description': 'Nitidez dos ângulos costofrênicos',
                    'rationale': 'Ângulos obliterados indicam derrame ou má técnica',
                    'implementation': 'Detector de cantos + medida de sharpness',
                    'priority': 'medium'
                }
            ],
            'ct': [
                {
                    'name': 'hu_uniformity',
                    'description': 'Uniformidade de HU em regiões homogêneas',
                    'rationale': 'Variação excessiva indica ruído ou artefato',
                    'implementation': 'ROI em músculo/parênquima + std HU',
                    'priority': 'high'
                },
                {
                    'name': 'slice_thickness_consistency',
                    'description': 'Consistência da espessura do slice',
                    'rationale': 'Variação indica erro no protocolo',
                    'implementation': 'Metadados DICOM + verificação',
                    'priority': 'high'
                },
                {
                    'name': 'streak_artifact_detector',
                    'description': 'Detector de artefatos em linha (metal)',
                    'rationale': 'Artefatos de metal degradam imagem',
                    'implementation': 'Transformada de Hough + detecção de linhas radiais',
                    'priority': 'medium'
                }
            ],
            'us': [
                {
                    'name': 'contact_quality_index',
                    'description': 'Qualidade do contato gel-sonda-pele',
                    'rationale': 'Mau contato gera sombras acústicas',
                    'implementation': 'Análise de regiões pretas na superfície',
                    'priority': 'high'
                },
                {
                    'name': 'depth_penetration_ratio',
                    'description': 'Razão de penetração vs ganho',
                    'rationale': 'Ganho excessivo com penetração ruim = ruído',
                    'implementation': 'Histograma vertical + análise de SNR por profundidade',
                    'priority': 'high'
                }
            ],
            'mri': [
                {
                    'name': 'ghosting_artifact_index',
                    'description': 'Índice de ghosting (movimento)',
                    'rationale': 'Movimento do paciente é principal artefato',
                    'implementation': 'Análise de repetição periódica no k-space',
                    'priority': 'high'
                },
                {
                    'name': 'signal_uniformity_map',
                    'description': 'Mapa de uniformidade do sinal',
                    'rationale': 'Coil ruim gera hotspots/coldspots',
                    'implementation': 'Filtro passa-baixa + análise de variação espacial',
                    'priority': 'high'
                }
            ]
        }
        
        for metric in suggestions.get(modality, []):
            print(f"\n📌 {metric['name']}")
            print(f"   Descrição: {metric['description']}")
            print(f"   Justificativa: {metric['rationale']}")
            print(f"   Implementação: {metric['implementation']}")
            print(f"   Prioridade: {metric['priority']}")
            
        return suggestions.get(modality, [])
    
    def optimize_hyperparameters(self, X, y, modality='rx'):
        """Otimiza hiperparâmetros do Random Forest."""
        print(f"\n{'='*70}")
        print(f"Otimização de Hiperparâmetros — {modality.upper()}")
        print(f"{'='*70}")
        
        param_grid = {
            'n_estimators': [100, 200, 300],
            'max_depth': [10, 15, 20, None],
            'min_samples_split': [2, 5, 10],
            'min_samples_leaf': [1, 2, 4]
        }
        
        rf = RandomForestRegressor(random_state=42, n_jobs=-1)
        
        grid_search = GridSearchCV(
            rf, param_grid, 
            cv=3, 
            scoring='neg_mean_absolute_error',
            n_jobs=-1,
            verbose=1
        )
        
        print("Iniciando busca em grid...")
        grid_search.fit(X, y)
        
        print(f"\n✅ Melhores parâmetros:")
        print(f"   {grid_search.best_params_}")
        print(f"   MAE: {-grid_search.best_score_:.3f}")
        
        return grid_search.best_estimator_, grid_search.best_params_
    
    def adversarial_validation(self, model, X_clean, X_degraded, y_clean, y_degraded):
        """Valida modelo contra imagens degradadas."""
        print(f"\n{'='*70}")
        print("Validação Adversarial")
        print(f"{'='*70}")
        
        # Predições
        pred_clean = model.predict(X_clean)
        pred_degraded = model.predict(X_degraded)
        
        # Métricas
        mae_clean = mean_absolute_error(y_clean, pred_clean)
        mae_degraded = mean_absolute_error(y_degraded, pred_degraded)
        
        print(f"MAE em imagens limpas:     {mae_clean:.3f}")
        print(f"MAE em imagens degradadas: {mae_degraded:.3f}")
        print(f"Degradação detectada:      {(pred_degraded < pred_clean).mean()*100:.1f}%")
        
        return {
            'mae_clean': mae_clean,
            'mae_degraded': mae_degraded,
            'detection_rate': (pred_degraded < pred_clean).mean()
        }
    
    def generate_research_report(self):
        """Gera relatório completo de research."""
        report = {
            'timestamp': pd.Timestamp.now().isoformat(),
            'models_analyzed': [],
            'suggested_metrics': {},
            'recommendations': []
        }
        
        # Analisa modelos existentes
        for modality in ['rx', 'us', 'ct', 'mri']:
            metrics = self.suggest_new_metrics(modality)
            report['suggested_metrics'][modality] = metrics
        
        # Recomendações gerais
        report['recommendations'] = [
            "Implementar métricas de symmetria para RX (clavicle_symmetry, lung_symmetry)",
            "Adicionar detecção de ghosting em MRI",
            "Criar índice de qualidade de contato para US",
            "Implementar detector de streak artifacts em CT",
            "Coletar labels de radiologistas para validação clínica",
            "Testar ensemble de modelos (RF + XGBoost + Ridge)",
            "Implementar calibração de threshold com Isotonic Regression"
        ]
        
        # Salva relatório
        report_file = Path("analysis_results/auto_research_report.json")
        report_file.parent.mkdir(exist_ok=True)
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"\n📄 Relatório salvo em: {report_file}")
        return report


def main():
    """Executa auto-research completo."""
    research = MIQAAutoResearch()
    
    # 1. Analisa modelos existentes
    research.analyze_all_models()
    
    # 2. Sugere novas métricas para cada modalidade
    for modality in ['rx', 'us', 'ct', 'mri']:
        research.suggest_new_metrics(modality)
    
    # 3. Gera relatório
    report = research.generate_research_report()
    
    print("\n" + "=" * 70)
    print("Auto-Research Completo!")
    print("=" * 70)
    print(f"\nPróximos passos:")
    print("1. Implementar métricas sugeridas de alta prioridade")
    print("2. Re-treinar modelos com novas features")
    print("3. Validar com radiologistas")
    print("4. Otimizar hiperparâmetros por modalidade")


if __name__ == "__main__":
    main()
