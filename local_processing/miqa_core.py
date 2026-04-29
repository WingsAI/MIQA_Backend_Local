import numpy as np
from typing import Dict, Any, Union
import os

from .heuristics.mri import MRIMetrics
from .heuristics.ct import CTMetrics
from .heuristics.us import USMetrics
from .preprocessing.artifact_removal import ArtifactRemover

class MIQAAnalyzer:
    """
    Medical Image Quality Assessment (MIQA) Core Analyzer.
    
    REGRA: Apenas modelos lightweight em CPU (Random Forest, XGBoost).
    Nenhuma rede neural. Modelos são carregados com antecedência para evitar cold start.
    """

    def __init__(self, model_path: str = None):
        self.artifact_remover = ArtifactRemover()
        self.models = {}  # Cache de modelos por (modality, body_part)
        
        # Pré-carrega modelos disponíveis
        self._preload_models()

    def _preload_models(self):
        """Carrega todos os modelos disponíveis no startup para evitar cold start."""
        try:
            from miqa.ml_models import list_available_models, load_model
            available = list_available_models()
            
            for modality, body_parts in available.items():
                for body_part, models in body_parts.items():
                    for model_info in models:
                        model_type = model_info["name"]
                        key = (modality, body_part)
                        
                        # Carrega modelo
                        data = load_model(modality, body_part, model_type)
                        if data:
                            self.models[key] = data
                            print(f"MIQA: Pre-loaded {modality}/{body_part}/{model_type}")
            
            if not self.models:
                print("MIQA: Nenhum modelo treinado encontrado. Usando fallback heurístico.")
            else:
                print(f"MIQA: {len(self.models)} modelos carregados")
        except Exception as e:
            print(f"MIQA: Erro carregando modelos: {e}")
            self.models = {}

    def analyze(self, image: np.ndarray, modality: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Main entry point for quality analysis.
        
        Args:
            image: 2D numpy array (grayscale).
            modality: 'mri', 'ct', or 'us'.
            metadata: DICOM metadata (PixelSpacing, etc).
        
        Returns:
            Dictionary containing extracted features and quality score.
        """
        # 1. Sanitize Image
        clean_image, artifact_mask = self.artifact_remover.sanitization_pipeline(image)
        
        features = {}
        
        # 2. Extract Features based on Modality
        if modality.lower() == 'mri':
            features = self._extract_mri_features(clean_image, metadata)
        elif modality.lower() == 'ct':
            features = self._extract_ct_features(clean_image, metadata)
        elif modality.lower() == 'us':
            features = self._extract_us_features(clean_image, metadata)
        else:
            raise ValueError(f"Unsupported modality: {modality}")
            
        # Add common artifact metrics
        features['artifact_area_ratio'] = np.sum(artifact_mask > 0) / image.size
        
        # 3. Predict Score using lightweight model
        body_part = self._detect_body_part(image, modality, metadata)
        score = self._predict_with_model(features, modality, body_part)
        
        return {
            "score": score,
            "features": features,
            "modality": modality,
            "body_part": body_part,
            "status": "success"
        }

    def _detect_body_part(self, image: np.ndarray, modality: str, metadata: Dict) -> str:
        """Detecta parte do corpo a partir de metadados ou heurísticas."""
        if metadata and "BodyPartExamined" in metadata:
            return metadata["BodyPartExamined"].lower()
        
        # Fallback simples por modalidade
        defaults = {
            "mri": "brain",
            "ct": "chest",
            "us": "abdomen"
        }
        return defaults.get(modality.lower(), "unknown")

    def _predict_with_model(self, features: Dict[str, float], modality: str, body_part: str) -> float:
        """Prediz score usando modelo lightweight ou fallback."""
        key = (modality.lower(), body_part.lower())
        
        # Tenta usar modelo treinado
        if key in self.models:
            try:
                model_data = self.models[key]
                model = model_data["model"]
                feature_names = model_data["feature_names"]
                
                # Prepara features
                import pandas as pd
                X = pd.DataFrame([features])
                
                # Garante colunas corretas
                for col in feature_names:
                    if col not in X.columns:
                        X[col] = 0.0
                X = X[feature_names]
                
                # Prediz
                score = model.predict(X)[0]
                return float(np.clip(score, 0, 100))
            except Exception as e:
                print(f"Prediction failed: {e}, using fallback")
                return self._heuristic_fallback_score(features, modality)
        
        # Fallback heurístico
        return self._heuristic_fallback_score(features, modality)

    def _extract_mri_features(self, image: np.ndarray, metadata: Dict) -> Dict[str, float]:
        """Extracts MRI-specific physics heuristics."""
        feats = {}
        
        threshold = np.mean(image) * 0.5
        background_mask = image < threshold
        tissue_mask = image >= threshold
        
        feats['snr_dietrich'] = MRIMetrics.calculate_dietrich_snr(image[tissue_mask], image[background_mask])
        feats['efc'] = MRIMetrics.calculate_efc(image)
        feats['ghosting_ratio'] = MRIMetrics.calculate_ghosting_ratio(image, background_mask=background_mask)
        feats['cjv_proxy'] = 0.0
        
        return feats

    def _extract_ct_features(self, image: np.ndarray, metadata: Dict) -> Dict[str, float]:
        """Extracts CT-specific physics heuristics."""
        feats = {}
        
        feats['air_deviation'] = CTMetrics.calculate_air_deviation(image)
        feats['quantum_mottle'] = CTMetrics.calculate_quantum_mottle(image)
        feats['erd'] = CTMetrics.calculate_erd(image)
        feats['nps_score'] = CTMetrics.calculate_nps_proxy(image)
        
        return feats

    def _extract_us_features(self, image: np.ndarray, metadata: Dict) -> Dict[str, float]:
        """Extracts US-specific physics heuristics."""
        feats = {}
        
        feats['speckle_index'] = USMetrics.calculate_speckle_index(image)
        feats['shadowing_score'] = USMetrics.detect_shadowing_dropout(image)
        feats['depth_gradient'] = USMetrics.calculate_depth_gradient(image)
        
        return feats

    def _heuristic_fallback_score(self, features: Dict[str, float], modality: str) -> float:
        """
        Fallback heurístico quando não há modelo treinado.
        """
        score = 50.0
        
        if modality == 'mri':
            if features.get('snr_dietrich', 0) > 10: score += 10
            if features.get('ghosting_ratio', 1) < 1.1: score += 10
            score -= features.get('efc', 0) * 10
            
        elif modality == 'ct':
            if features.get('quantum_mottle', 0) < 50: score += 10
            if features.get('air_deviation', 100) < 10: score += 10
            
        elif modality == 'us':
            if 1.8 < features.get('speckle_index', 0) < 2.0: score += 20
            score += features.get('shadowing_score', 0) * 20
            
        return max(0.0, min(score, 100.0))
