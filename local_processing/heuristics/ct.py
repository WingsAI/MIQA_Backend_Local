import numpy as np
import cv2
from scipy import ndimage

class CTMetrics:
    """
    Implements Section 2.3: Tomografia Computadorizada (TC) Metrics
    Focus: Density (Hounsfield Units) and Geometry.
    """

    @staticmethod
    def calculate_air_deviation(image: np.ndarray, air_threshold: float = -900) -> float:
        """
        Calculates deviation from expected Air HU (-1000).
        Assuming image is already converted to HU.
        If image is normalized 0-1 or 0-255, this needs calibration metadata.
        For this function, we assume the input `image` IS in Hounsfield Units.
        
        Heuristic: Segment external air, calculate mean, compare to -1000.
        """
        # Create mask for air (e.g., everything below -900 HU)
        # Note: In a raw DICOM image, air is background. 
        # A simple segmentation of the "outside" is needed.
        
        mask_air = image < air_threshold
        if np.sum(mask_air) == 0:
            return 1000.0 # Huge error if no air found
            
        mean_air_hu = np.mean(image[mask_air])
        
        # Expected is -1000
        deviation = abs(mean_air_hu - (-1000))
        return deviation

    @staticmethod
    def calculate_quantum_mottle(image: np.ndarray, roi_mask: np.ndarray = None) -> float:
        """
        Quantum Mottle (Noise) proxy.
        Std dev in a homogeneous region (ROI).
        """
        if roi_mask is not None:
            roi_pixels = image[roi_mask]
            if len(roi_pixels) > 0:
                return np.std(roi_pixels)
        
        # If no mask, try to find a homogeneous region automatically?
        # For now, return global std dev of a central crop (assuming tissue) could be a fallback,
        # but that includes structure. 
        # Better fallback: std dev of the air region (though strictly mottle is seen in tissue).
        # Let's use a small sliding window to find the region with lowest variance (most homogeneous).
        
        # Sliding window variance
        local_std = ndimage.generic_filter(image, np.std, size=10)
        # The lowest variances correspond to homogeneous regions
        # We average the lowest 10% of variances to estimate noise floor
        noise_floor = np.mean(np.sort(local_std.flatten())[:int(local_std.size * 0.1)])
        return noise_floor

    @staticmethod
    def calculate_erd(image: np.ndarray, edge_roi: np.ndarray = None) -> float:
        """
        Edge Rise Distance (ERD).
        Distance in pixels to go from 10% to 90% intensity across a high-contrast edge (bone/tissue).
        """
        # If no ROI provided, we need to find a sharp edge.
        # Use Canny to find edges, then analyze gradient profile.
        
        # 1. Gradient magnitude
        grad_x = cv2.Sobel(image, cv2.CV_64F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(image, cv2.CV_64F, 0, 1, ksize=3)
        magnitude = np.sqrt(grad_x**2 + grad_y**2)
        
        # Find strongest edge pixel
        if edge_roi is not None:
            # Mask magnitude
            magnitude = magnitude * edge_roi
            
        max_loc = np.unravel_index(np.argmax(magnitude), magnitude.shape)
        
        # Extract profile perpendicular to edge at max_loc? 
        # Simplified: Extract a small 10x10 patch around max edge and measure mean transition width.
        # Even simpler for heuristic: Inverse of max gradient magnitude.
        # Implementation of full ERD requires precise edge orientation.
        
        # Proxy: 
        max_grad = np.max(magnitude)
        if max_grad == 0:
            return 10.0 # High blur
            
        # ERD is inversely proportional to gradient slope.
        # If intensity jumps 1000 HU in 1 pixel => Slope 1000 => ERD low.
        # If intensity jumps 1000 HU in 5 pixels => Slope 200 => ERD high.
        # We return a score related to width.
        
        return 1.0 / max_grad # Normalized score needed later

    @staticmethod
    def calculate_nps_proxy(image: np.ndarray) -> float:
        """
        Noise Power Spectrum (NPS) texture proxy.
        High frequency power relative to total power.
        """
        f = np.fft.fft2(image)
        fshift = np.fft.fftshift(f)
        magnitude_spectrum = 20 * np.log(np.abs(fshift) + 1e-8)
        
        h, w = image.shape
        center_y, center_x = h // 2, w // 2
        
        # Define High Frequency region (outer ring)
        y, x = np.ogrid[:h, :w]
        dist_from_center = np.sqrt((x - center_x)**2 + (y - center_y)**2)
        
        # High freq mask (e.g., > 1/4 of calc freq)
        mask_high = dist_from_center > (min(h, w) / 4)
        
        avg_high_freq_power = np.mean(magnitude_spectrum[mask_high])
        avg_total_power = np.mean(magnitude_spectrum)
        
        if avg_total_power == 0: 
            return 0.0
            
        # Ratio of high frequency noise
        return avg_high_freq_power / avg_total_power
