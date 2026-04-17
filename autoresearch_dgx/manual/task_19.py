"""Task 19 — Data quality metrics (SNR, contrast, Laplacian variance) por imagem do test set.

Output: image_quality.csv  [dataset, split, idx, mean, std, snr, contrast, laplacian_var]
        image_quality_summary.json
"""
import numpy as np
import pandas as pd
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
from _utils import set_seed, DATASET_CLASSES, save_csv, save_json, emit_result

# numpy-only Laplacian fallback (3x3 kernel)
LAP_KERNEL = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)

def laplacian_var(img_u8: np.ndarray) -> float:
    if HAS_CV2:
        return float(cv2.Laplacian(img_u8, cv2.CV_32F).var())
    # scipy-less convolution via padding + sliding window
    img = img_u8.astype(np.float32)
    h, w = img.shape
    pad = np.pad(img, 1, mode="edge")
    out = np.zeros_like(img)
    for i in range(3):
        for j in range(3):
            out += LAP_KERNEL[i, j] * pad[i:i+h, j:j+w]
    return float(out.var())

set_seed(42)
rows = []

# usamos as_rgb=False para pegar os grayscale originais (8-bit)
for name, cls in DATASET_CLASSES.items():
    for split in ["test"]:
        ds = cls(split=split, download=True, size=28, as_rgb=False)
        imgs = np.asarray(ds.imgs)
        if imgs.ndim == 3:
            imgs = imgs[..., None]  # [N, H, W, 1]
        print(f"{name} {split} imgs shape={imgs.shape}")

        for i in range(imgs.shape[0]):
            img = imgs[i, :, :, 0].astype(np.float32)
            mean = float(img.mean())
            std = float(img.std())
            snr = float(mean / (std + 1e-6))
            contrast = float((img.max() - img.min()) / 255.0)
            lap_var = laplacian_var(img.astype(np.uint8))
            rows.append({
                "dataset": name, "split": split, "idx": int(i),
                "mean": round(mean, 3), "std": round(std, 3),
                "snr": round(snr, 3), "contrast": round(contrast, 4),
                "laplacian_var": round(lap_var, 2),
            })

df = pd.DataFrame(rows)
save_csv(df, "image_quality.csv")

# resumo por dataset (flatten em estrutura JSON-friendly)
summary = {}
for ds_name, g in df.groupby("dataset"):
    summary[ds_name] = {
        col: {
            "mean": round(float(g[col].mean()), 3),
            "median": round(float(g[col].median()), 3),
            "std": round(float(g[col].std()), 3),
        }
        for col in ["mean", "std", "snr", "contrast", "laplacian_var"]
    }
save_json(summary, "image_quality_summary.json")

emit_result("n_images", len(df))
emit_result("mean_snr", f"{df['snr'].mean():.3f}")
emit_result("mean_lap_var", f"{df['laplacian_var'].mean():.2f}")
