import numpy as np
import math

class MRIMetrics:
    """
    Implements Section 2.2: Ressonância Magnética (RM) Metrics
    """

    @staticmethod
    def calculate_dietrich_snr(roi_signal: np.ndarray, roi_air: np.ndarray) -> float:
        """
        Calculates SNR using Dietrich's method for Rician noise.
        SNR = mu_ROI / (sigma_air / sqrt(2 - pi/2))
        """
        mu_roi = np.mean(roi_signal)
        sigma_air = np.std(roi_air)
        
        # Rayleigh constant for Rician noise in background
        rayleigh_const = np.sqrt(2 - np.pi/2)
        
        if sigma_air == 0:
            return 0.0 # Avoid division by zero
            
        corrected_noise = sigma_air / rayleigh_const
        return mu_roi / corrected_noise

    @staticmethod
    def calculate_efc(image: np.ndarray) -> float:
        """
        Entropy Focus Criterion (EFC).
        """
        img_abs = np.abs(image)
        total_energy = np.sum(img_abs)
        
        if total_energy == 0:
            return 0.0
            
        p = img_abs / total_energy
        p = p[p > 0]
        
        shannon_entropy = -np.sum(p * np.log(p))
        
        n_pixels = image.size
        max_entropy = np.log(n_pixels)
        
        return shannon_entropy / max_entropy

    @staticmethod
    def calculate_ghosting_ratio(image: np.ndarray, phase_axis: int = 0, background_mask: np.ndarray = None) -> float:
        """
        Ghosting Ratio.
        """
        if background_mask is None:
            h, w = image.shape
            background_mask = np.zeros_like(image, dtype=bool)
            background_mask[:h//10, :] = True
            background_mask[-h//10:, :] = True
            background_mask[:, :w//10] = True
            background_mask[:, -w//10:] = True
            
        bg_pixels = image[background_mask]
        roi_mask = ~background_mask
        signal_mean = np.mean(image[roi_mask])
        bg_mean = np.mean(bg_pixels)
        
        if signal_mean == 0: 
            return 0.0
            
        return bg_mean / signal_mean

    @staticmethod
    def estimate_bias_field_cjv(image: np.ndarray, wm_mask: np.ndarray, gm_mask: np.ndarray) -> float:
        """
        Coefficient of Joint Variation (CJV).
        """
        wm_pixels = image[wm_mask]
        gm_pixels = image[gm_mask]
        
        if len(wm_pixels) == 0 or len(gm_pixels) == 0:
            return 0.0
            
        mu_wm = np.mean(wm_pixels)
        sigma_wm = np.std(wm_pixels)
        
        mu_gm = np.mean(gm_pixels)
        sigma_gm = np.std(gm_pixels)
        
        diff_mean = abs(mu_wm - mu_gm)
        
        if diff_mean == 0:
            return 100.0 # Worst case
            
        return (sigma_wm + sigma_gm) / diff_mean
