"""Novas métricas anatomy-aware sugeridas pelo auto-research pipeline.

Métricas implementadas:
- clavicle_symmetry: Simetria da clavícula (RX)
- rib_count_visibility: Contagem de costelas visíveis (RX)
- hu_uniformity: Uniformidade de HU (CT)
- ghosting_artifact_index: Índice de ghosting (MRI)
- signal_uniformity_map: Mapa de uniformidade do sinal (MRI)

Uso:
    from miqa.anatomy.metrics_advanced import (
        compute_clavicle_symmetry,
        compute_hu_uniformity,
        compute_ghosting_index
    )
"""

import numpy as np
import cv2
from scipy import ndimage
from scipy.fft import fft2, fftshift
from typing import Dict, Optional, Tuple


def compute_clavicle_symmetry(img: np.ndarray) -> Optional[float]:
    """Mede a simetria da clavícula para detectar rotação do paciente.
    
    Args:
        img: Imagem normalizada [0, 1]
        
    Returns:
        Score de simetria [0, 1] onde 1 = perfeitamente simétrico
    """
    h, w = img.shape
    
    # Região superior do tórax (onde fica a clavícula)
    y_start = int(h * 0.15)
    y_end = int(h * 0.35)
    clavicle_region = img[y_start:y_end, :]
    
    # Divide em hemisférios
    mid = w // 2
    left = clavicle_region[:, :mid]
    right = clavicle_region[:, mid:]
    
    # Equaliza tamanhos
    min_w = min(left.shape[1], right.shape[1])
    left = left[:, -min_w:]
    right = right[:, :min_w]
    
    # Espelha o lado direito
    right_flipped = np.fliplr(right)
    
    # Calcula correlação
    correlation = np.corrcoef(left.flatten(), right_flipped.flatten())[0, 1]
    
    # Normaliza para [0, 1]
    symmetry_score = max(0, correlation)
    
    return float(symmetry_score)


def compute_rib_count_visibility(img: np.ndarray) -> Optional[int]:
    """Conta o número de costelas visíveis acima do diafragma.
    
    Args:
        img: Imagem normalizada [0, 1]
        
    Returns:
        Número de costelas detectadas (aproximado)
    """
    h, w = img.shape
    
    # Região lateral do tórax
    y_start = int(h * 0.3)
    y_end = int(h * 0.7)
    
    # Analisa ambos os lados
    left_region = img[y_start:y_end, :w//3]
    right_region = img[y_start:y_end, 2*w//3:]
    
    def count_ribs(region):
        # Aplica filtro para destacar bordas horizontais (costelas)
        sobel_y = cv2.Sobel((region * 255).astype(np.uint8), cv2.CV_64F, 0, 1, ksize=3)
        
        # Projeção vertical
        projection = np.abs(sobel_y).mean(axis=1)
        
        # Enconca picos (costelas)
        from scipy.signal import find_peaks
        peaks, _ = find_peaks(projection, distance=10, prominence=5)
        
        return len(peaks)
    
    left_ribs = count_ribs(left_region)
    right_ribs = count_ribs(right_region)
    
    # Média dos dois lados
    avg_ribs = (left_ribs + right_ribs) / 2
    
    return int(avg_ribs)


def compute_hu_uniformity(img: np.ndarray, hu_values: Optional[np.ndarray] = None) -> Optional[float]:
    """Mede a uniformidade de HU em regiões homogêneas.
    
    Args:
        img: Imagem em HU (ou normalizada se hu_values não fornecido)
        hu_values: Imagem em unidades Hounsfield (opcional)
        
    Returns:
        Coeficiente de variação da uniformidade (menor = mais uniforme)
    """
    if hu_values is not None:
        img_hu = hu_values
    else:
        # Se não tiver HU, usa a imagem normalizada (aproximação)
        img_hu = img * 1000 - 500  # Aproximação grosseira
    
    h, w = img_hu.shape
    
    # Região central (assume-se que é tecido mole/parênquima)
    y_start, y_end = int(h*0.3), int(h*0.7)
    x_start, x_end = int(w*0.3), int(w*0.7)
    center_region = img_hu[y_start:y_end, x_start:x_end]
    
    # Calcula desvio padrão local
    local_std = ndimage.generic_filter(center_region, np.std, size=15)
    
    # Uniformidade é inversamente proporcional ao desvio
    uniformity = 1.0 / (1.0 + np.mean(local_std))
    
    return float(uniformity)


def compute_ghosting_index(img: np.ndarray) -> Optional[float]:
    """Detecta artefatos de ghosting (movimento) em MRI.
    
    Args:
        img: Imagem normalizada [0, 1]
        
    Returns:
        Índice de ghosting [0, 1] onde 1 = muito ghosting
    """
    h, w = img.shape
    
    # Análise no domínio da frequência
    f_transform = fftshift(fft2(img))
    magnitude = np.abs(f_transform)
    
    # Ghosting aparece como picos periódicos no espectro
    # Analisa projeções horizontal e vertical
    h_profile = magnitude.sum(axis=1)
    v_profile = magnitude.sum(axis=0)
    
    def detect_periodicity(profile):
        # Autocorrelação
        profile = profile - profile.mean()
        autocorr = np.correlate(profile, profile, mode='full')
        autocorr = autocorr[len(autocorr)//2:]
        
        # Normaliza
        autocorr = autocorr / autocorr[0]
        
        # Procura picos secundários (periodicidade)
        from scipy.signal import find_peaks
        peaks, properties = find_peaks(autocorr[5:], height=0.1, distance=10)
        
        if len(peaks) > 0:
            return np.max(properties['peak_heights'])
        return 0.0
    
    h_ghosting = detect_periodicity(h_profile)
    v_ghosting = detect_periodicity(v_profile)
    
    # Ghosting médio
    ghosting_score = (h_ghosting + v_ghosting) / 2
    
    return float(min(1.0, ghosting_score * 5))  # Escala para [0, 1]


def compute_signal_uniformity(img: np.ndarray) -> Optional[float]:
    """Mapa de uniformidade do sinal para MRI.
    
    Args:
        img: Imagem normalizada [0, 1]
        
    Returns:
        Score de uniformidade [0, 1] onde 1 = muito uniforme
    """
    # Aplica filtro passa-baixa para suavizar
    img_smooth = ndimage.gaussian_filter(img, sigma=5)
    
    # Calcula variação local
    local_var = ndimage.generic_filter(img_smooth, np.var, size=20)
    
    # Uniformidade é inversamente proporcional à variação
    uniformity = 1.0 / (1.0 + np.mean(local_var) * 10)
    
    return float(uniformity)


def compute_contact_quality(img: np.ndarray) -> Optional[float]:
    """Avalia a qualidade do contato gel-sonda-pele em ultrassom.
    
    Args:
        img: Imagem normalizada [0, 1]
        
    Returns:
        Score de qualidade do contato [0, 1]
    """
    h, w = img.shape
    
    # Região superior (próxima à sonda)
    top_region = img[:h//4, :]
    
    # Áreas pretas indicam mau contato (sombras acústicas na superfície)
    dark_areas = (top_region < 0.1).sum() / top_region.size
    
    # Score inversamente proporcional às áreas escuras
    contact_score = 1.0 - dark_areas
    
    return float(contact_score)


def compute_depth_penetration_ratio(img: np.ndarray) -> Optional[float]:
    """Avalia a razão de penetração vs ruído em ultrassom.
    
    Args:
        img: Imagem normalizada [0, 1]
        
    Returns:
        Razão de penetração [0, 1]
    """
    h, w = img.shape
    
    # Analisa intensidade média por profundidade
    depths = []
    intensities = []
    
    for y in range(0, h, 20):
        row = img[y, :]
        depths.append(y / h)
        intensities.append(np.mean(row))
    
    depths = np.array(depths)
    intensities = np.array(intensities)
    
    # Penetração é onde a intensidade cai abaixo de um threshold
    threshold = 0.3
    penetration_indices = np.where(intensities < threshold)[0]
    
    if len(penetration_indices) > 0:
        penetration_depth = depths[penetration_indices[0]]
    else:
        penetration_depth = 1.0
    
    return float(penetration_depth)


# Mapeamento de métricas por modalidade
METRICS_REGISTRY = {
    'rx': {
        'clavicle_symmetry': compute_clavicle_symmetry,
        'rib_count_visibility': compute_rib_count_visibility,
    },
    'ct': {
        'hu_uniformity': compute_hu_uniformity,
    },
    'mri': {
        'ghosting_artifact_index': compute_ghosting_index,
        'signal_uniformity_map': compute_signal_uniformity,
    },
    'us': {
        'contact_quality_index': compute_contact_quality,
        'depth_penetration_ratio': compute_depth_penetration_ratio,
    }
}


def compute_advanced_metrics(img: np.ndarray, modality: str) -> Dict[str, Optional[float]]:
    """Computa todas as métricas avançadas para uma modalidade.
    
    Args:
        img: Imagem normalizada [0, 1]
        modality: 'rx', 'ct', 'mri', 'us'
        
    Returns:
        Dict com nome_da_métrica -> valor
    """
    results = {}
    
    metrics = METRICS_REGISTRY.get(modality, {})
    
    for name, func in metrics.items():
        try:
            value = func(img)
            if value is not None:
                results[name] = value
        except Exception as e:
            # Falha silenciosa - métrica não aplicável
            pass
    
    return results
