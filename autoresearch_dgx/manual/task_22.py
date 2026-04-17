"""Task 22 — Test-Time Augmentation (TTA).
Compara clean vs TTA-ensemble (horizontal flip + 2 small rotations) em 3 datasets.

Output: tta_gains.csv  [dataset, method, accuracy, macro_auc]
"""
import numpy as np
import pandas as pd
import torch
import torchvision.transforms.functional as TF
from sklearn.metrics import roc_auc_score
from _utils import (set_seed, quick_loaders, build_model, train_short,
                    DEVICE, save_csv, emit_result)

set_seed(42)
DATASETS = ["chestmnist", "breastmnist", "organamnist"]
rows = []

def get_probs(model, x, task):
    logits = model(x)
    if task == "multi-label, binary-class":
        return torch.sigmoid(logits)
    return torch.softmax(logits, 1)

for name in DATASETS:
    loaders, info = quick_loaders(name, batch=128, size=28)
    task = info["task"]
    n_classes = len(info["label"])
    print(f"\n=== TTA on {name} ===")
    model = build_model("resnet18", n_classes, pretrained=True)
    train_short(model, loaders, task, epochs=3, lr=1e-3)
    model.eval()

    clean_probs, tta_probs, labels = [], [], []
    with torch.no_grad():
        for x, y in loaders["test"]:
            x = x.to(DEVICE)
            p_clean = get_probs(model, x, task).cpu().numpy()
            # TTA: average of flipped + rotations
            p_flip = get_probs(model, torch.flip(x, [3]), task).cpu().numpy()
            p_rot1 = get_probs(model, TF.rotate(x, 10), task).cpu().numpy()
            p_rotm = get_probs(model, TF.rotate(x, -10), task).cpu().numpy()
            p_tta = (p_clean + p_flip + p_rot1 + p_rotm) / 4.0
            clean_probs.append(p_clean); tta_probs.append(p_tta)
            labels.append(np.asarray(y))

    P_clean = np.concatenate(clean_probs, 0)
    P_tta = np.concatenate(tta_probs, 0)
    Y = np.concatenate(labels, 0)

    def metrics(probs):
        if task == "multi-label, binary-class":
            preds = (probs >= 0.5).astype(np.int32)
            y = np.asarray(Y).astype(np.int32)
            acc = float((preds == y).all(axis=1).mean())
            aucs = [roc_auc_score(y[:, i], probs[:, i]) for i in range(y.shape[1]) if len(np.unique(y[:, i])) >= 2]
            auc = float(np.mean(aucs))
        else:
            preds = probs.argmax(1)
            y = np.asarray(Y).astype(np.int64).reshape(-1)
            acc = float((preds == y).mean())
            try:
                auc = float(roc_auc_score(y, probs, multi_class="ovr", average="macro"))
            except Exception:
                auc = float("nan")
        return acc, auc

    acc_c, auc_c = metrics(P_clean)
    acc_t, auc_t = metrics(P_tta)
    rows += [
        {"dataset": name, "method": "clean", "accuracy": round(acc_c, 4), "macro_auc": round(auc_c, 4)},
        {"dataset": name, "method": "tta_4view", "accuracy": round(acc_t, 4), "macro_auc": round(auc_t, 4)},
    ]
    print(rows[-2]); print(rows[-1])

df = pd.DataFrame(rows)
save_csv(df, "tta_gains.csv")
# delta auc medio
d = df.pivot(index="dataset", columns="method", values="macro_auc")
emit_result("mean_auc_gain", f"{(d['tta_4view'] - d['clean']).mean():.4f}")
