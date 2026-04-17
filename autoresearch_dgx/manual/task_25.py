"""Task 25 — Regularizacao: CE baseline vs CE+label smoothing (0.1) vs Mixup (alpha=0.2).
So em OrganAMNIST (multi-class) por simplicidade.

Output: regularization.csv  [method, macro_auc, accuracy, macro_f1]
"""
import time
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from _utils import (set_seed, quick_loaders, build_model, evaluate, DEVICE,
                    save_csv, emit_result)

set_seed(42)
NAME = "organamnist"
EPOCHS = 3
loaders, info = quick_loaders(NAME, batch=128, size=28)
task = info["task"]
n_classes = len(info["label"])
rows = []

def train_method(method):
    set_seed(42)
    model = build_model("resnet18", n_classes, pretrained=True).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    t0 = time.time()
    for ep in range(EPOCHS):
        model.train()
        for x, y in loaders["train"]:
            x = x.to(DEVICE)
            y_t = torch.tensor(np.asarray(y).reshape(-1), dtype=torch.long, device=DEVICE)

            if method == "mixup":
                lam = np.random.beta(0.2, 0.2)
                idx = torch.randperm(x.size(0), device=DEVICE)
                x_mix = lam * x + (1 - lam) * x[idx]
                logits = model(x_mix)
                loss = lam * F.cross_entropy(logits, y_t) + (1 - lam) * F.cross_entropy(logits, y_t[idx])
            elif method == "ls":
                logits = model(x)
                loss = F.cross_entropy(logits, y_t, label_smoothing=0.1)
            else:
                logits = model(x)
                loss = F.cross_entropy(logits, y_t)

            opt.zero_grad(); loss.backward(); opt.step()
    return model, time.time() - t0

for method in ["baseline", "ls", "mixup"]:
    print(f"\n=== {method} ===")
    model, sec = train_method(method)
    res = evaluate(model, loaders["test"], task)
    row = {"method": method,
           "macro_auc": round(res["macro_auc"], 4),
           "accuracy": round(res["accuracy"], 4),
           "macro_f1": round(res["macro_f1"], 4),
           "seconds": round(sec, 1)}
    print(row); rows.append(row)

df = pd.DataFrame(rows)
save_csv(df, "regularization.csv")
best = df.sort_values("macro_auc", ascending=False).iloc[0]
emit_result("best_method", best["method"])
emit_result("best_auc", f"{best['macro_auc']:.4f}")
