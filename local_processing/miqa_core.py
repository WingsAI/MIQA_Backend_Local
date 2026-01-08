import numpy as np
from typing import Dict, Any, Union
import joblib
import pandas as pd
import os
from .heuristics.mri import MRIMetrics
from .heuristics.ct import CTMetrics
from .heuristics.us import USMetrics
from .preprocessing.artifact_removal import ArtifactRemover

class MIQAAnalyzer:
    """
    Medical Image Quality Assessment (MIQA) Core Analyzer.
    """

    def __init__(self, model_path: str = "miqa_rf_model.pkl"):
        self.artifact_remover = ArtifactRemover()
        self.model = None
        if os.path.exists(model_path):
            try:
                self.model = joblib.load(model_path)
                print(f"MIQA: Loaded Random Forest model from {model_path}")
            except Exception as e:
                print(f"MIQA: Failed to load model: {e}")

    def analyze(self, image: np.ndarray, modality: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Main entry point for quality analysis.
        
        Args:
            image: 2D numpy array (grayscale).
            modality: 'mri', 'ct', or 'us'.
            metadata: DICOM metadata (PixelSpacing, etc).
        
        Returns:
            Dictionary containing extracted features and (optionally) quality score.
        """
        # 1. Sanitize Image
        # clean_image, mask = self.artifact_remover.sanitization_pipeline(image)
        # For metric calculation, we might want to use the clean image for texture,
        # but keep awareness of artifacts. 
        # For now, let's calculate metrics on the "clean" image to avoid text skewing results.
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
        
        # 3. Predict Score
        if self.model:
            # Prepare dataframe for prediction (ensure column order matches training?)
            # RF is sensitive to column order if using array, but DF handles names.
            # Assuming training used the same keys.
            try:
                # Convert features to DF
                df_feat = pd.DataFrame([features])
                # Fill NAs
                df_feat = df_feat.fillna(0)
                
                # Check for missing columns that model expects?
                # For now rely on sklearn to complain or just work if features match
                predicted_score = self.model.predict(df_feat)[0]
                # Clamp
                score = max(0.0, min(predicted_score, 100.0))
            except Exception as e:
                print(f"Prediction failed: {e}, using fallback")
                score = self._heuristic_fallback_score(features, modality)
        else:
            score = self._heuristic_fallback_score(features, modality)
        
        return {
            "score": score,
            "features": features,
            "modality": modality,
            "status": "success"
        }

    def _extract_mri_features(self, image: np.ndarray, metadata: Dict) -> Dict[str, float]:
        """Extracts MRI-specific physics heuristics."""
        feats = {}
        
        # Heuristics require some segmentation (Air vs Tissue). 
        # Simple thresholding for prototype.
        threshold = np.mean(image) * 0.5
        background_mask = image < threshold
        tissue_mask = image >= threshold
        
        # Dietrich SNR
        feats['snr_dietrich'] = MRIMetrics.calculate_dietrich_snr(image[tissue_mask], image[background_mask])
        
        # EFC
        feats['efc'] = MRIMetrics.calculate_efc(image)
        
        # Ghosting (simplified)
        feats['ghosting_ratio'] = MRIMetrics.calculate_ghosting_ratio(image, background_mask=background_mask)
        
        # CJV (Needs GM/WM segmentation - placeholder)
        # We would need multi-otsu or k-means here to find GM/WM.
        feats['cjv_proxy'] = 0.0 # To be implemented with segmentation logic
        
        return feats

    def _extract_ct_features(self, image: np.ndarray, metadata: Dict) -> Dict[str, float]:
        """Extracts CT-specific physics heuristics."""
        feats = {}
        
        # Air Deviation
        feats['air_deviation'] = CTMetrics.calculate_air_deviation(image)
        
        # Quantum Mottle
        feats['quantum_mottle'] = CTMetrics.calculate_quantum_mottle(image)
        
        # ERD
        feats['erd'] = CTMetrics.calculate_erd(image)
        
        # NPS
        feats['nps_score'] = CTMetrics.calculate_nps_proxy(image)
        
        return feats

    def _extract_us_features(self, image: np.ndarray, metadata: Dict) -> Dict[str, float]:
        """Extracts US-specific physics heuristics."""
        feats = {}
        
        # Speckle Index
        feats['speckle_index'] = USMetrics.calculate_speckle_index(image)
        
        # Shadowing
        feats['shadowing_score'] = USMetrics.detect_shadowing_dropout(image)
        
        # Depth Gradient
        feats['depth_gradient'] = USMetrics.calculate_depth_gradient(image)
        
        return feats

    def _heuristic_fallback_score(self, features: Dict[str, float], modality: str) -> float:
        """
        Temporary linear combination of features to generate a dummy score 
        before the Random Forest is trained.
        """
        score = 50.0 # Base
        
        # Very rough logic just to see numbers move
        if modality == 'mri':
            if features.get('snr_dietrich', 0) > 10: score += 10
            if features.get('ghosting_ratio', 1) < 1.1: score += 10
            score -= features.get('efc', 0) * 10
            
        elif modality == 'ct':
            if features.get('noise_floor', 0) < 50: score += 10
            if features.get('air_deviation', 100) < 10: score += 10
            
        elif modality == 'us':
            if 1.8 < features.get('speckle_index', 0) < 2.0: score += 20
            score += features.get('shadowing_score', 0) * 20
            
        return max(0.0, min(score, 100.0))
