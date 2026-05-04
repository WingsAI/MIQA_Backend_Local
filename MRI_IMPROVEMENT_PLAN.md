# Plano de Melhoria: Modelo MRI

## Diagnóstico do Problema

### Métricas Atuais (MRI Brain v2)
- **Train R²:** 0.918
- **Val R²:** 0.776
- **Val MAE:** 8.03 pontos
- **Overfitting:** 0.142 (diferença train-val) — **ALTO**

### Bug Crítico Identificado

As features do modelo MRI incluem **métricas de RX** que são irrelevantes:

```python
# Features atuais do modelo MRI:
[
    "u_niqe",                           # OK — universal
    "u_brisque",                        # OK — universal
    "img_mean", "img_std", "img_entropy",  # OK — básicas
    "adv_ghosting_artifact_index",      # OK — MRI-specific
    "adv_signal_uniformity_map",        # OK — MRI-specific
    "a_rx_skull.penetration_index",     # BUG — é de RX!
    "a_rx_skull.sinus_air_score",       # BUG — é de RX!
    "a_rx_abdomen.nps_fat",             # BUG — é de RX!
    "a_rx_abdomen.free_air_detector",   # BUG — é de RX!
    "a_rx_chest.lung_symmetry",         # BUG — é de RX!
    "a_rx_chest.inspiration_index",     # BUG — é de RX!
    "a_rx_chest.mediastinum_width",     # BUG — é de RX!
    "a_rx_chest.rotation_angle"         # BUG — é de RX!
]
```

**6 das 15 features (40%) são de RX** e sempre retornam 0/NaN para MRI. Isso:
- Adiciona ruído ao modelo
- Força o RF a aprender padrões espúrios
- Reduz capacidade de generalização

---

## Plano de Ação

### 1. Corrigir Features (Prioridade CRÍTICA)

**Problema:** `extract_features()` não filtra features por modalidade.

**Solução:** Criar extractor específico para MRI:

```python
# miqa/ml_models/mri_features.py

def extract_mri_features(image_path):
    """Extrai apenas features relevantes para MRI."""
    features = {}
    
    # 1. Features universais
    features['u_niqe'] = compute_niqe(image_path)
    features['u_brisque'] = compute_brisque(image_path)
    features['img_mean'] = np.mean(img)
    features['img_std'] = np.std(img)
    features['img_entropy'] = shannon_entropy(img)
    
    # 2. Features MRI-specific
    features['ghosting_index'] = compute_ghosting(img)
    features['signal_uniformity'] = compute_uniformity(img)
    features['snr'] = compute_snr(img)
    features['contrast_t1_t2'] = estimate_contrast(img)
    features['motion_artifacts'] = detect_motion(img)
    features['susceptibility_artifacts'] = detect_susceptibility(img)
    
    # 3. Features anatômicas (se detectado)
    anatomy = detect_anatomy(image_path)
    if anatomy.modality == 'mri':
        if anatomy.body_part == 'brain':
            features['gray_white_contrast'] = compute_gray_white(img)
            features['ventricle_visibility'] = detect_ventricles(img)
            features['cortex_definition'] = measure_cortex(img)
    
    return features
```

**Features MRI específicas a implementar:**

| Feature | Descrição | Expectativa |
|---------|-----------|-------------|
| `snr_dietrich` | SNR usando método Dietrich | Alto impacto |
| `ghosting_ratio` | Artefatos de ghosting | Alto impacto |
| `signal_uniformity` | Uniformidade do sinal | Médio impacto |
| `contrast_t1_t2` | Contraste T1/T2 | Alto impacto |
| `motion_score` | Detecção de movimento | Médio impacto |
| `susceptibility_index` | Artefatos de susceptibilidade | Médio impacto |
| `gray_white_ratio` | Contraste substância cinza/branca | Alto (brain) |
| `ventricle_contrast` | Visibilidade dos ventrículos | Médio (brain) |

### 2. Aumentar Regularização do Random Forest

**Problema:** Overfitting alto (train R² 0.918 vs val R² 0.776)

**Solução:** Ajustar hiperparâmetros:

```python
# Antes (provavelmente):
RandomForestRegressor(
    n_estimators=100,
    max_depth=None,  # Sem limite = overfitting
    min_samples_split=2,  # Muito baixo
)

# Depois:
RandomForestRegressor(
    n_estimators=200,  # Mais árvores para estabilidade
    max_depth=10,  # Limitar profundidade
    min_samples_split=10,  # Evitar split em folhas pequenas
    min_samples_leaf=5,  # Folhas com no mínimo 5 amostras
    max_features='sqrt',  # Subset de features por árvore
    bootstrap=True,
    oob_score=True,  # Out-of-bag para validação
)
```

### 3. Validar com Out-of-Bag (OOB)

```python
# OOB score é uma validação "gratuita" durante treino
rf = RandomForestRegressor(oob_score=True, ...)
rf.fit(X_train, y_train)
print(f"OOB R²: {rf.oob_score_:.3f}")  # Deve ser próximo do val R²
```

### 4. Augmentation Específico para MRI

**Problema:** MRI tem artefatos únicos que outros não têm.

**Novas degradações MRI:**

```python
# miqa/ml_models/augmentation.py

def add_ghosting_artifact(img, intensity=0.3):
    """Simula ghosting em MRI (replicação periódica)."""
    shifted = np.roll(img, img.shape[0] // 4, axis=0)
    return img * (1 - intensity) + shifted * intensity

def add_susceptibility_artifact(img, intensity=0.4):
    """Simula artefatos de susceptibilidade (próximo a ossos/metal)."""
    # Cria região de distorção geométrica
    y, x = np.ogrid[:img.shape[0], :img.shape[1]]
    mask = ((x - img.shape[1]//2)**2 / (img.shape[1]//4)**2 + 
            (y - img.shape[0]//2)**2 / (img.shape[0]//4)**2) < 1
    distorted = img.copy()
    distorted[mask] = distorted[mask] * (1 - intensity)
    return distorted

def add_chemical_shift(img, intensity=0.2):
    """Deslocamento químico em MRI (bordas de gordura)."""
    edges = sobel(img)
    return img + edges * intensity * np.max(img)

def add_rf_interference(img, intensity=0.15):
    """Interferência de RF (zipper artifacts)."""
    # Adiciona linhas verticais/horizontais
    artifact = np.zeros_like(img)
    for i in range(0, img.shape[1], 20):
        artifact[:, i:i+2] = intensity * np.max(img)
    return np.clip(img + artifact, 0, 1)
```

### 5. Teacher Score Específico para MRI

**Problema:** Teacher score atual pode não ser adequado para MRI.

**Solução:** Ponderar métricas MRI:

```python
def compute_mri_teacher_score(features):
    """Score de qualidade específico para MRI."""
    score = 100
    
    # SNR é crítico em MRI
    if 'snr' in features:
        snr = features['snr']
        if snr < 10:
            score -= 30
        elif snr < 20:
            score -= 15
        elif snr < 30:
            score -= 5
    
    # Ghosting é muito problemático
    if 'ghosting_index' in features:
        ghost = features['ghosting_index']
        if ghost > 0.1:
            score -= 25
        elif ghost > 0.05:
            score -= 10
    
    # Uniformidade do sinal
    if 'signal_uniformity' in features:
        uni = features['signal_uniformity']
        if uni < 0.7:
            score -= 20
        elif uni < 0.85:
            score -= 8
    
    # Contraste (especialmente para brain)
    if 'gray_white_ratio' in features:
        gwr = features['gray_white_ratio']
        if gwr < 0.5 or gwr > 2.0:
            score -= 15
    
    # Artefatos de movimento
    if 'motion_score' in features:
        motion = features['motion_score']
        if motion > 0.2:
            score -= 20
    
    return max(0, min(100, score))
```

### 6. Feature Selection

**Remover features com baixa importância:**

```python
from sklearn.feature_selection import SelectFromModel

# Treinar modelo inicial
rf = RandomForestRegressor(n_estimators=100)
rf.fit(X_train, y_train)

# Selecionar features importantes
selector = SelectFromModel(rf, threshold="mean", prefit=True)
X_train_selected = selector.transform(X_train)
X_val_selected = selector.transform(X_val)

# Re-treinar com features selecionadas
rf_final = RandomForestRegressor(n_estimators=200, ...)
rf_final.fit(X_train_selected, y_train)
```

### 7. Cross-Validação Estratificada

**Problema:** Validação simples pode não refletir a distribuição real.

**Solução:** K-Fold estratificado por tipo de tumor (se houver labels):

```python
from sklearn.model_selection import StratifiedKFold

# Se tivermos labels de tumor:
# cv = StratifiedKFold(n_splits=5, shuffle=True)
# scores = cross_val_score(rf, X, y, cv=cv, scoring='r2')

# Ou K-Fold normal:
from sklearn.model_selection import cross_val_score, KFold
cv = KFold(n_splits=5, shuffle=True, random_state=42)
scores = cross_val_score(rf, X, y, cv=cv, scoring='r2')
print(f"CV R²: {scores.mean():.3f} (+/- {scores.std():.3f})")
```

### 8. Ensemble de Modelos

**Treinar múltiplos modelos e combinar:**

```python
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge

# Random Forest
rf = RandomForestRegressor(n_estimators=200, max_depth=10, ...)
rf.fit(X_train, y_train)

# Gradient Boosting
gb = GradientBoostingRegressor(n_estimators=100, max_depth=4, ...)
gb.fit(X_train, y_train)

# Ridge Regression (para capturar relações lineares)
ridge = Ridge(alpha=1.0)
ridge.fit(X_train, y_train)

# Ensemble simples (média)
def ensemble_predict(X):
    pred_rf = rf.predict(X)
    pred_gb = gb.predict(X)
    pred_ridge = ridge.predict(X)
    return (pred_rf + pred_gb + pred_ridge) / 3

val_pred = ensemble_predict(X_val)
val_r2 = r2_score(y_val, val_pred)
print(f"Ensemble Val R²: {val_r2:.3f}")
```

---

## Timeline de Implementação

### Fase 1: Correção de Bug (1-2h)
- [ ] Identificar onde features RX estão sendo adicionadas
- [ ] Criar `extract_mri_features()` específico
- [ ] Remover features cross-modal do extractor
- [ ] Re-treinar modelo rápido para testar impacto

### Fase 2: Novas Features MRI (3-4h)
- [ ] Implementar `snr_dietrich` para MRI
- [ ] Implementar `gray_white_ratio`
- [ ] Implementar `ventricle_contrast`
- [ ] Implementar `motion_score`
- [ ] Testar cada feature individualmente

### Fase 3: Augmentation MRI (2h)
- [ ] Adicionar `ghosting_artifact` augmentation
- [ ] Adicionar `susceptibility_artifact`
- [ ] Adicionar `chemical_shift`
- [ ] Adicionar `rf_interference`
- [ ] Balancear amostras por tipo de artefato

### Fase 4: Hiperparâmetros (1h)
- [ ] Ajustar max_depth, min_samples_split, min_samples_leaf
- [ ] Testar n_estimators: 100, 200, 500
- [ ] Usar GridSearchCV ou OOB para validação
- [ ] Implementar feature selection

### Fase 5: Validação (1h)
- [ ] K-Fold cross-validation
- [ ] Verificar distribuição de scores
- [ ] Calibrate scores se necessário
- [ ] Testar em imagens reais

**Total estimado: 8-10 horas de trabalho**

---

## Expectativa de Resultados

| Métrica | Atual | Esperado | Melhoria |
|---------|-------|----------|----------|
| Val R² | 0.776 | **0.85+** | +0.074 |
| Val MAE | 8.03 | **<6.0** | -25% |
| Train-Val Gap | 0.142 | **<0.08** | -44% |

---

## Código de Referência: Novas Features MRI

```python
# miqa/anatomy/mri_metrics.py

import numpy as np
from scipy import ndimage
from skimage import filters, measure

def compute_mri_snr(image):
    """
    SNR para MRI usando método do sinal/branco.
    ROI central = sinal, cantos = ruído.
    """
    h, w = image.shape
    
    # ROI central (sinal)
    center_roi = image[h//4:3*h//4, w//4:3*w//4]
    signal_mean = np.mean(center_roi)
    
    # Cantos (ruído)
    corners = [
        image[:h//4, :w//4],
        image[:h//4, -w//4:],
        image[-h//4:, :w//4],
        image[-h//4:, -w//4:]
    ]
    noise_std = np.std(np.concatenate([c.flatten() for c in corners]))
    
    snr = signal_mean / max(noise_std, 1e-9)
    return snr

def compute_gray_white_contrast(image):
    """
    Mede contraste entre matéria cinza e branca (brain MRI).
    Assume que o cérebro está centralizado.
    """
    h, w = image.shape
    center = image[h//4:3*h//4, w//4:3*w//4]
    
    # Threshold para separar tecidos
    thresh = filters.threshold_otsu(center)
    
    # Matéria branca (mais brilhante)
    white_matter = center[center > thresh * 1.2]
    # Matéria cinza (intermediário)
    gray_matter = center[(center >= thresh * 0.8) & (center <= thresh * 1.2)]
    
    if len(white_matter) == 0 or len(gray_matter) == 0:
        return 0.0
    
    wm_mean = np.mean(white_matter)
    gm_mean = np.mean(gray_matter)
    
    contrast = abs(wm_mean - gm_mean) / max(wm_mean + gm_mean, 1e-9)
    return contrast

def detect_ventricles(image):
    """
    Detecta ventrículos laterais (regiões escuras em T1, brilhantes em T2).
    Retorna score de visibilidade.
    """
    h, w = image.shape
    center = image[h//3:2*h//3, w//3:2*w//3]
    
    # Ventrículos são regiões escuras em T1
    dark_regions = center < np.percentile(center, 25)
    
    # Devem ter formato oval e ser 2 regiões simétricas
    labeled = ndimage.label(dark_regions)[0]
    regions = measure.regionprops(labeled)
    
    if len(regions) >= 2:
        # Score baseado em tamanho e simetria
        areas = [r.area for r in regions[:2]]
        centroids = [r.centroid for r in regions[:2]]
        
        symmetry = 1 - abs(areas[0] - areas[1]) / max(sum(areas), 1)
        visibility = min(np.mean(areas) / 100, 1.0)  # Normalizado
        
        return (symmetry + visibility) / 2
    
    return 0.0

def measure_cortex_thickness(image):
    """
    Mede espessura do córtex cerebral.
    Córtex bem definido = boa qualidade.
    """
    edges = filters.sobel(image)
    
    # Córtex tem bordas fortes e consistentes
    edge_strength = np.mean(edges)
    edge_uniformity = 1 - np.std(edges) / max(np.mean(edges), 1e-9)
    
    return edge_strength * edge_uniformity

def detect_motion_artifacts(image):
    """
    Detecta artefatos de movimento (ghosting periódico).
    """
    fft = np.fft.fft2(image)
    fft_shift = np.fft.fftshift(fft)
    magnitude = np.abs(fft_shift)
    
    # Movimento cria linhas no espectro de frequência
    center_y, center_x = magnitude.shape[0]//2, magnitude.shape[1]//2
    
    # Verificar picos periódicos ao longo de kx e ky
    kx_profile = magnitude[center_y, :]
    ky_profile = magnitude[:, center_x]
    
    # Detectar picos fora do centro (artefatos)
    kx_peaks = np.sum(kx_profile > np.percentile(kx_profile, 95)) / len(kx_profile)
    ky_peaks = np.sum(ky_profile > np.percentile(ky_profile, 95)) / len(ky_profile)
    
    motion_score = (kx_peaks + ky_peaks) / 2
    return motion_score
```

---

## Checklist de Execução

### Hoje (2-3h)
- [ ] Corrigir bug de features RX no MRI
- [ ] Adicionar SNR e contraste gray-white
- [ ] Re-treinar modelo com features corrigidas
- [ ] Medir impacto: esperado +0.05-0.10 em R²

### Amanhã (3-4h)
- [ ] Implementar augmentation MRI-specific
- [ ] Adicionar detect_ventricles e measure_cortex
- [ ] Ajustar hiperparâmetros do RF
- [ ] Re-treinar com mais augmentation

### Depois (2-3h)
- [ ] Feature selection (remover low-importance)
- [ ] Cross-validation estratificada
- [ ] Teste em imagens reais
- [ ] Documentar novo modelo

**Quer que eu comece a implementar agora? Posso começar pela correção do bug de features (maior impacto imediato).**
