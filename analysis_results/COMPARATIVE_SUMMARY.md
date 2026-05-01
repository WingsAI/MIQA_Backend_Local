# 📊 MIQA Dataset Analysis — Comparative Summary

**Date:** 2026-04-30
**Method:** Heavy augmentation (13 degradation types) + Random Forest

---

## 🏆 Model Performance (v2 — MAX images)

| Dataset | Images | Val MAE | Val R² | Features |
|---------|--------|---------|--------|----------|
| **RX / Chest** | 2,000 | 8.59 | 0.828 | 7 |
| **US / Breast** | 780 | 4.32 | 0.913 | 7 |
| **CT / Chest** | 2,000 | 6.97 | 0.862 | 7 |
| **MRI / Brain** | 2,000 | 8.09 | 0.768 | 7 |

---

## 📈 Score Statistics by Dataset

### RX Chest (COVID-19 Radiography)
- **Mean:** 68.5 | **Std:** 12.2 | **Range:** 44.1 – 90.7
- **Validation MAE:** 3.91 on 50 real images
- **Top Feature:** BRISQUE (71.2% importance)

### US Breast (BUSI)
- **Mean:** 64.3 | **Std:** 15.8 | **Range:** 28.2 – 88.4
- **Validation MAE:** 0.12 on 50 real images
- **Top Feature:** NIQE (86.6% importance)

### CT Chest (COVID CT)
- **Mean:** 71.2 | **Std:** 10.4 | **Range:** 52.1 – 89.3
- **Validation:** Model not yet loaded for prediction
- **Top Feature:** BRISQUE (77.7% importance)

### MRI Brain (Brain Tumor)
- **Mean:** 59.8 | **Std:** 18.2 | **Range:** 31.5 – 91.2
- **Validation:** Model not yet loaded for prediction
- **Top Feature:** NIQE (41.0% importance)

---

## 🎨 Degradation Impact

| Degradation | Avg Score Drop | Most Affected |
|-------------|---------------|---------------|
| noise_salt_pepper | -59.5 points | ALL |
| blur_motion | -55.9 points | ALL |
| blur_gaussian | -55.3 points | ALL |
| noise_gaussian | -34.3 points | ALL |
| ring_artifact | -30.1 points | CT/MRI |
| jpeg | -22.8 points | ALL |
| contrast_low | -18.4 points | ALL |
| vignetting | -18.6 points | ALL |
| brightness_dark | -13.9 points | ALL |

---

## 🔑 Key Insights

1. **BRISQUE + NIQE dominate:** Together they explain 60-95% of model decisions
2. **US has best model:** Lowest MAE (4.32) and highest R² (0.913)
3. **MRI is hardest:** Highest variance (std=18.2) due to diverse tumor types
4. **Salt & pepper noise** is the most destructive degradation across all modalities
5. **Anatomy-aware metrics** contribute 5-15% additional predictive power

---

## 📁 Generated Files

```
analysis_results/
├── rx/chest/
│   ├── statistics.json
│   ├── score_distributions.png
│   ├── quality_examples.png
│   └── validation_results.png
├── us/breast/
│   ├── statistics.json
│   ├── score_distributions.png
│   ├── quality_examples.png
│   └── validation_results.png
├── ct/chest/
│   ├── statistics.json
│   ├── score_distributions.png
│   └── quality_examples.png
└── mri/brain/
    ├── statistics.json
    ├── score_distributions.png
    ├── quality_examples.png
    └── correlation_plot.png
```

---

## 🚀 Next Steps

1. Train on remaining 40,330 RX images (current: 2,000)
2. Add more anatomy-aware features per context
3. Collect radiologist labels for clinical threshold calibration
4. Deploy to Railway with volume-mounted models
