"""Task 26 — Focal loss vs BCE no ChestMNIST (multi-label com class imbalance).

Output: focal_vs_bce.csv  [method, gamma, macro_auc, macro_f1, accuracy]
"""
import time
import json
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from _utils import (set_seed, quick_loaders, build_model, evaluate, DEVICE,
                    save_csv, emit_result)

set_seed(42)
NAME = "chestmnist"
EPOCHS = 3
loaders, info = quick_loaders(NAME, batch=128, size=28)
task = info["task"]
n_classes = len(info["label"])

class FocalLoss(nn.Module):
    def __init__(self, gamma=2.0):
        super().__init__(); self.gamma = gamma
    def forward(self, logits, target):
        # target [N,C] binary
        p = torch.sigmoid(logits)
        ce = F.binary_cross_entropy_with_logits(logits, target, reduction="none")
        pt = p * target + (1 - p) * (1 - target)
        return (((1 - pt) ** self.gamma) * ce).mean()

def train_method(loss_fn):
    set_seed(42)
    model = build_model("resnet18", n_classes, pretrained=True).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    t0 = time.time()
    for ep in range(EPOCHS):
        model.train()
        for x, y in loaders["train"]:
            x = x.to(DEVICE)
            y_t = torch.tensor(y, dtype=torch.float32, device=DEVICE)
            loss = loss_fn(model(x), y_t)
            opt.zero_grad(); loss.backward(); opt.step()
    return model, time.time() - t0

configs = [
    ("bce", 0.0, nn.BCEWithLogitsLoss()),
    ("focal", 1.0, FocalLoss(gamma=1.0)),
    ("focal", 2.0, FocalLoss(gamma=2.0)),
]

rows = []
all_per_label = {}
for method, gamma, fn in configs:
    print(f"\n=== {method} gamma={gamma} ===")
    model, sec = train_method(fn)
    res = evaluate(model, loaders["test"], task)
    row = {"method": method, "gamma": gamma,
           "macro_auc": round(res["macro_auc"], 4),
           "macro_f1": round(res["macro_f1"], 4),
           "accuracy": round(res["accuracy"], 4),
           "seconds": round(sec, 1)}
    print(row); rows.append(row)
    all_per_label[f"{method}_g{gamma}"] = [round(float(a), 4) for a in res["per_label_auc"]]

df = pd.DataFrame(rows)
save_csv(df, "focal_vs_bce.csv")
with open(f"{__import__('_utils').EXP_DIR}/focal_vs_bce_per_label.json", "w") as f:
    json.dump(all_per_label, f, indent=2)
emit_result("best_macro_auc", f"{df['macro_auc'].max():.4f}")
emit_result("best_cfg",
            f"{df.loc[df['macro_auc'].idxmax(), 'method']}_g{df.loc[df['macro_auc'].idxmax(), 'gamma']}")
