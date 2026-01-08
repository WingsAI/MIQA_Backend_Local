import cv2
import numpy as np
from typing import Tuple

class ArtifactRemover:
    """
    Implements Pre-processing Critical: Removal of Non-Anatomical Artifacts.
    """

    def __init__(self):
        pass

    def detect_text_and_lines(self, image: np.ndarray) -> np.ndarray:
        """
        Detects burnt-in text and scale lines.
        """
        if image.dtype != np.uint8:
            src_img = (image * 255).astype(np.uint8)
        else:
            src_img = image.copy()

        edges = cv2.Canny(src_img, 100, 200)

        kernel_text = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        dilated = cv2.dilate(edges, kernel_text, iterations=2)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        mask = np.zeros((src_img.shape[0], src_img.shape[1]), dtype=np.uint8)
        
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            aspect_ratio = w / float(h)
            area = cv2.contourArea(cnt)
            
            is_text_block = (10 < area < 2000)
            is_line = (aspect_ratio > 5 or aspect_ratio < 0.2) and (w > 20 or h > 20)
            
            if is_text_block or is_line:
                cv2.drawContours(mask, [cnt], -1, 255, -1)
                
        mask = cv2.dilate(mask, kernel_text, iterations=1)
            
        return mask

    def apply_inpainting(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """
        Restores the image using Telea inpainting.
        """
        if image.dtype != np.uint8:
            src_img = (image * 255).astype(np.uint8)
            was_float = True
        else:
            src_img = image
            was_float = False
            
        if mask.dtype != np.uint8:
            mask = mask.astype(np.uint8)

        inpainted = cv2.inpaint(src_img, mask, 3, cv2.INPAINT_TELEA)

        if was_float:
            return inpainted.astype(np.float32) / 255.0
        return inpainted

    def sanitization_pipeline(self, image: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Runs the full detection + inpainting pipeline.
        """
        mask = self.detect_text_and_lines(image)
        clean_image = self.apply_inpainting(image, mask)
        return clean_image, mask
