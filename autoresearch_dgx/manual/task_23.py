"""Task 23 — MC Dropout uncertainty.
Wrap ResNet18 com Dropout2d antes do classifier e faz N forward passes com dropout ativo.
Correla variance com error pra checar se e uma good uncertainty measure.

Output: uncertainty.csv  [dataset, metric, value]
"""
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from scipy.stats import pointbiserialr, spearmanr
from _utils import (set_seed, quick_loaders, build_model, train_short,
                    DEVICE, save_csv, emit_result)

set_seed(42)
N_MC = 10
DATASETS = ["breastmnist", "organamnist"]  # skip chest multilabel pra simplificar
rows = []

class MCWrapper(nn.Module):
    def __init__(self, base, p=0.3):
        super().__init__()
        self.base = base
        self.drop = nn.Dropout(p)
        # hackeamos o forward pra intercalar dropout antes do fc (resnet18)
        self.fc_orig = self.base.fc
        self.base.fc = nn.Identity()
    def forward(self, x):
        feat = self.base(x)
        feat = self.drop(feat)
        return self.fc_orig(feat)

for name in DATASETS:
    loaders, info = quick_loaders(name, batch=128, size=28)
    task = info["task"]
    print(f"\n=== MC Dropout on {name} ===")
    model = build_model("resnet18", len(info["label"]), pretrained=True)
    train_short(model, loaders, task, epochs=3, lr=1e-3)
    mc = MCWrapper(model).to(DEVICE)
    mc.train()  # mantém dropout ativo mesmo no "eval"

    all_entropies, all_correct, all_preds = [], [], []
    with torch.no_grad():
        for x, y in loaders["test"]:
            x = x.to(DEVICE)
            probs_mc = []
            for _ in range(N_MC):
                logits = mc(x)
                probs_mc.append(torch.softmax(logits, 1).cpu().numpy())
            mean = np.stack(probs_mc, 0).mean(axis=0)
            entropy = -np.sum(mean * np.log(mean + 1e-12), axis=1)
            preds = mean.argmax(1)
            y_np = np.asarray(y).astype(np.int64).reshape(-1)
            correct = (preds == y_np).astype(np.int32)
            all_entropies.append(entropy); all_correct.append(correct); all_preds.append(preds)

    H = np.concatenate(all_entropies)
    C = np.concatenate(all_correct)
    acc = float(C.mean())
    mean_ent_ok = float(H[C == 1].mean()) if (C == 1).any() else float("nan")
    mean_ent_wr = float(H[C == 0].mean()) if (C == 0).any() else float("nan")
    # correlacao: entropia deveria ser MAIOR quando preds errados
    try:
        rho, p = pointbiserialr(C, H)
    except Exception:
        rho, p = float("nan"), float("nan")
    row = {"dataset": name, "accuracy": round(acc, 4),
           "mean_entropy_correct": round(mean_ent_ok, 4),
           "mean_entropy_wrong": round(mean_ent_wr, 4),
           "point_biserial_rho": round(float(rho), 4),
           "n_mc": N_MC}
    print(row)
    rows.append(row)

df = pd.DataFrame(rows)
save_csv(df, "uncertainty.csv")
emit_result("mean_rho", f"{df['point_biserial_rho'].mean():.4f}")
