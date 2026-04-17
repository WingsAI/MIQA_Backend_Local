"""Task 24 — Transfer learning vs from-scratch nos 3 datasets, 3 epocas cada.

Output: transfer_vs_scratch.csv  [dataset, pretrained, macro_auc, accuracy, macro_f1, seconds]
"""
import pandas as pd
from _utils import (set_seed, quick_loaders, build_model, train_short,
                    evaluate, save_csv, emit_result)

set_seed(42)
DATASETS = ["chestmnist", "breastmnist", "organamnist"]
rows = []

for name in DATASETS:
    loaders, info = quick_loaders(name, batch=128, size=28)
    task = info["task"]
    for pretrained in [True, False]:
        print(f"\n=== {name} pretrained={pretrained} ===")
        set_seed(42)
        m = build_model("resnet18", len(info["label"]), pretrained=pretrained)
        sec = train_short(m, loaders, task, epochs=3, lr=1e-3)
        res = evaluate(m, loaders["test"], task)
        row = {"dataset": name, "pretrained": pretrained,
               "macro_auc": round(res["macro_auc"], 4),
               "accuracy": round(res["accuracy"], 4),
               "macro_f1": round(res["macro_f1"], 4),
               "seconds": round(sec, 1)}
        print(row)
        rows.append(row)

df = pd.DataFrame(rows)
save_csv(df, "transfer_vs_scratch.csv")
piv = df.pivot(index="dataset", columns="pretrained", values="macro_auc")
emit_result("mean_auc_gain_pretrain", f"{(piv[True] - piv[False]).mean():.4f}")
