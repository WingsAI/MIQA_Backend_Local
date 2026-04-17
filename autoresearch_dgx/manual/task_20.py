"""Task 20 — OOD detection: treina um modelo num dataset in-dist e testa OOD em outros.
Usa max-softmax-probability (MSP, Hendrycks & Gimpel 2017) como score OOD.

Output: ood_auc.csv  [in_dist, out_dist, auroc, auprc]
"""
import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader
from sklearn.metrics import roc_auc_score, average_precision_score
from _utils import (set_seed, quick_loaders, get_dataset, build_model, train_short,
                    DEVICE, save_csv, emit_result)

set_seed(42)
DATASETS = ["organamnist", "breastmnist", "chestmnist"]

# treina um modelo para cada dataset como in-distribution
rows = []
for in_name in DATASETS:
    print(f"\n=== In-dist: {in_name} ===")
    loaders, info = quick_loaders(in_name, batch=128, size=28)
    task = info["task"]
    model = build_model("resnet18", len(info["label"]), pretrained=True)
    train_short(model, loaders, task, epochs=3, lr=1e-3)
    model.eval()

    # Pega max softmax score (MSP) no test in-dist
    def msp_scores(loader, multilabel):
        scores = []
        with torch.no_grad():
            for x, _ in loader:
                x = x.to(DEVICE)
                logits = model(x)
                if multilabel:
                    # para multi-label, usamos max prob sigmoid como "confidence"
                    s = torch.sigmoid(logits).max(dim=1).values
                else:
                    s = torch.softmax(logits, dim=1).max(dim=1).values
                scores.append(s.cpu().numpy())
        return np.concatenate(scores)

    multilabel = task == "multi-label, binary-class"
    s_in = msp_scores(loaders["test"], multilabel)
    print(f"  in-dist MSP mean={s_in.mean():.3f}")

    for out_name in DATASETS:
        if out_name == in_name:
            continue
        out_ds, _ = get_dataset(out_name, split="test", size=28)
        out_dl = DataLoader(out_ds, batch_size=128, shuffle=False, num_workers=2)
        s_out = msp_scores(out_dl, multilabel)

        # in-dist deve ter score ALTO (confident), OOD deve ter BAIXO
        y = np.concatenate([np.ones_like(s_in), np.zeros_like(s_out)])
        scores = np.concatenate([s_in, s_out])
        auroc = float(roc_auc_score(y, scores))
        auprc = float(average_precision_score(y, scores))
        row = {"in_dist": in_name, "out_dist": out_name,
               "auroc": round(auroc, 4), "auprc": round(auprc, 4),
               "s_in_mean": round(float(s_in.mean()), 3),
               "s_out_mean": round(float(s_out.mean()), 3)}
        print(row)
        rows.append(row)

df = pd.DataFrame(rows)
save_csv(df, "ood_auc.csv")
emit_result("mean_ood_auroc", f"{df['auroc'].mean():.4f}")
