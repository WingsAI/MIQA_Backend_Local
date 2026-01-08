import numpy as np
from scipy import ndimage

class USMetrics:
    """
    Implements Section 2.4: Ultrassonografia (US) Metrics
    Focus: Speckle, Shadowing, Contact.
    """

    @staticmethod
    def calculate_speckle_index(image: np.ndarray, roi_mask: np.ndarray = None) -> float:
        """
        Speckle Index = mu / sigma.
        In fully developed speckle (Rayleigh), should be ~1.91.
        Deviation indicates post-processing (smoothing) or poor gain.
        """
        if roi_mask is None:
            # Use central region as proxy for "tissue"
            h, w = image.shape
            roi_mask = np.zeros_like(image, dtype=bool)
            roi_mask[h//4:3*h//4, w//4:3*w//4] = True
            
        roi_pixels = image[roi_mask]
        mu = np.mean(roi_pixels)
        sigma = np.std(roi_pixels)
        
        if sigma == 0:
            return 0.0 # Artificial region
            
        return mu / sigma

    @staticmethod
    def calculate_gcnr(region_a: np.ndarray, region_b: np.ndarray) -> float:
        """
        Generalized Contrast-to-Noise Ratio (gCNR).
        gCNR = 1 - overlap_area(histogram_A, histogram_B).
        """
        # Calculate histograms
        min_val = min(region_a.min(), region_b.min())
        max_val = max(region_a.max(), region_b.max())
        bins = np.linspace(min_val, max_val, 100)
        
        hist_a, _ = np.histogram(region_a, bins=bins, density=True)
        hist_b, _ = np.histogram(region_b, bins=bins, density=True)
        
        # Normalize to sum to 1 (probability mass) approx
        bin_width = bins[1] - bins[0]
        # pmf_a = hist_a * bin_width
        # pmf_b = hist_b * bin_width
        
        # Overlap area: integral of min(p_a, p_b)
        overlap = np.sum(np.minimum(hist_a, hist_b)) * bin_width
        
        return 1 - overlap

    @staticmethod
    def detect_shadowing_dropout(image: np.ndarray) -> float:
        """
        Detects vertical dark lines (acoustic shadowing/dropout).
        Heuristic: Column sums. Sudden drops in column sums indicate dropout.
        
        Returns: Score (0.0 to 1.0), where 1.0 means NO shadowing (clean), 
                 0.0 means severe shadowing.
        """
        # Sum along columns (axis 0)
        col_profile = np.sum(image, axis=0)
        
        # Smooth profile to remove local noise
        col_profile_smooth = ndimage.gaussian_filter1d(col_profile, sigma=5)
        
        # Calculate gradients (derivative)
        grads = np.diff(col_profile_smooth)
        
        # Identify strong negative gradients followed by low value plateau?
        # Simpler: Variance of the profile? 
        # Plan says: "Quedas abruptas e sustentadas na soma das colunas".
        
        mean_val = np.mean(col_profile_smooth)
        # Identify columns significantly below mean
        dropout_cols = np.sum(col_profile_smooth < (mean_val * 0.5))
        
        total_cols = image.shape[1]
        dropout_ratio = dropout_cols / total_cols
        
        return 1.0 - dropout_ratio

    @staticmethod
    def calculate_depth_gradient(image: np.ndarray) -> float:
        """
        Evaluates signal attenuation with depth.
        Linear regression of row-means.
        Expected: Slight decrease or flat (if TGC is correct).
        Steep decrease = Bad TGC or penetration failure.
        
        Returns: Slope (float). Negative values indicate attenuation.
        """
        row_means = np.mean(image, axis=1)
        
        # Normalize depth (0 to 1)
        x = np.linspace(0, 1, len(row_means))
        
        # Linear regression
        slope, intercept = np.polyfit(x, row_means, 1)
        
        return slope
