"""Task 30 — Relatorio final HTML agregando todos os CSVs/JSONs de tasks 15-29.

Output: miqa_final_report.html
"""
import os
import json
import glob
import pandas as pd
from _utils import EXP_DIR, emit_result

def load_csv(name):
    p = os.path.join(EXP_DIR, name)
    if not os.path.exists(p): return None
    try: return pd.read_csv(p)
    except Exception as e: print(f"load {name} error: {e}"); return None

def load_json(name):
    p = os.path.join(EXP_DIR, name)
    if not os.path.exists(p): return None
    try:
        with open(p) as f: return json.load(f)
    except Exception: return None

def embed_img(name):
    p = os.path.join(EXP_DIR, name)
    if os.path.exists(p):
        import base64
        with open(p, "rb") as f:
            b = base64.b64encode(f.read()).decode()
        return f'<img src="data:image/png;base64,{b}" style="max-width:100%"/>'
    return "<em>(missing)</em>"

sections = []
# ---- 15 ----
df = load_csv("chestmnist_resnet18.csv")
summ = load_json("chestmnist_resnet18_summary.json")
if df is not None:
    sections.append(("15 · ResNet18 ChestMNIST (5 epochs)",
        f"<p>Macro AUC: <b>{summ['macro_auc']:.4f}</b> · acc {summ['accuracy']:.4f} · f1 {summ['macro_f1']:.4f}</p>"
        + df.head(15).to_html(index=False, float_format=lambda x: f'{x:.4f}')))

# ---- 16 ----
df = load_csv("benchmark_3x3.csv")
if df is not None:
    sections.append(("16 · Benchmark 3 datasets × 3 architectures",
        df.to_html(index=False, float_format=lambda x: f'{x:.4f}')))

# ---- 17 meta ----
meta = load_json("features_resnet18_meta.json")
if meta:
    sections.append(("17 · Feature extraction (ResNet18, 512-d)",
        "<ul>" + "".join([f"<li><b>{k}</b>: {v}</li>" for k, v in meta.items()]) + "</ul>"))

# ---- 18 ----
imgs = ""
for img in ["embeddings_tsne.png", "embeddings_umap.png"]:
    if os.path.exists(os.path.join(EXP_DIR, img)):
        imgs += f"<h4>{img}</h4>" + embed_img(img)
if imgs:
    sections.append(("18 · Embeddings projections (t-SNE / UMAP)", imgs))

# ---- 19 ----
df = load_csv("image_quality.csv")
summ = load_json("image_quality_summary.json")
if df is not None:
    s = df.groupby("dataset")[["snr", "contrast", "laplacian_var"]].mean().round(3)
    sections.append(("19 · Image quality metrics",
        f"<p>n={len(df)} images scored across 3 datasets.</p>" + s.to_html()))

# ---- 20 ----
df = load_csv("ood_auc.csv")
if df is not None:
    sections.append(("20 · OOD detection (MSP score)", df.to_html(index=False)))

# ---- 21 ----
df = load_csv("adv_fgsm.csv")
if df is not None:
    sections.append(("21 · FGSM adversarial robustness", df.to_html(index=False)))

# ---- 22 ----
df = load_csv("tta_gains.csv")
if df is not None:
    sections.append(("22 · Test-time augmentation", df.to_html(index=False)))

# ---- 23 ----
df = load_csv("uncertainty.csv")
if df is not None:
    sections.append(("23 · MC Dropout uncertainty", df.to_html(index=False)))

# ---- 24 ----
df = load_csv("transfer_vs_scratch.csv")
if df is not None:
    sections.append(("24 · Transfer learning vs from-scratch", df.to_html(index=False)))

# ---- 25 ----
df = load_csv("regularization.csv")
if df is not None:
    sections.append(("25 · Regularization (CE vs LS vs Mixup)", df.to_html(index=False)))

# ---- 26 ----
df = load_csv("focal_vs_bce.csv")
if df is not None:
    sections.append(("26 · Focal loss vs BCE (ChestMNIST)", df.to_html(index=False)))

# ---- 27 ----
df = load_csv("distillation.csv")
if df is not None:
    sections.append(("27 · Knowledge distillation", df.to_html(index=False)))

# ---- 28 ----
df = load_csv("quantization.csv")
if df is not None:
    sections.append(("28 · INT8 dynamic quantization", df.to_html(index=False)))

# ---- 29 ----
if os.path.exists(os.path.join(EXP_DIR, "gradcam_samples.png")):
    sections.append(("29 · Grad-CAM samples (OrganAMNIST)",
        embed_img("gradcam_samples.png")))

# inventario de arquivos
files = sorted(f for f in os.listdir(EXP_DIR) if not f.startswith("."))
inventory = f"<p><b>{len(files)} files</b></p><ul>" + \
            "".join([f"<li>{f}</li>" for f in files]) + "</ul>"
sections.append(("Inventory", inventory))

# render
html = ["<!doctype html><html><head><meta charset='utf-8'><title>MIQA Final Report</title>",
        "<style>body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#222;line-height:1.5}h1{border-bottom:3px solid #76b900;padding-bottom:0.5rem}h2{color:#76b900;margin-top:2rem;border-bottom:1px solid #eee;padding-bottom:4px}table{border-collapse:collapse;margin:1rem 0;font-size:0.85rem}td,th{border:1px solid #ddd;padding:6px 10px;text-align:left}th{background:#f5f5f5}img{border:1px solid #ddd;border-radius:6px;margin:0.5rem 0}</style></head><body>",
        "<h1>MIQA Backend — AutoResearch Report (Manual tasks 15-30)</h1>",
        "<p>Gerado automaticamente por <code>task_30.py</code>.</p>"]
for title, body in sections:
    html.append(f"<h2>{title}</h2>{body}")
html.append("</body></html>")
out = os.path.join(EXP_DIR, "miqa_final_report.html")
with open(out, "w") as f: f.write("\n".join(html))
print(f"SAVED: {out}")
emit_result("sections", len(sections))
