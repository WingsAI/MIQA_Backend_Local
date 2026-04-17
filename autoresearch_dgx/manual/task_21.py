"""Task 21 — Adversarial robustness via FGSM em varios epsilons.
Modelo: ResNet18 pretrained + 3 epocas fine-tune em cada dataset.

Output: adv_fgsm.csv  [dataset, epsilon, accuracy, macro_auc]
"""
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from sklearn.metrics import roc_auc_score
from _utils import (set_seed, quick_loaders, build_model, train_short,
                    DEVICE, save_csv, emit_result, get_loss_fn)

set_seed(42)
EPS_LIST = [0.0, 0.01, 0.03, 0.1]
DATASETS = ["breastmnist", "organamnist"]   # skipa chest (multilabel + mais lento) p/ caber no tempo
rows = []

for name in DATASETS:
    loaders, info = quick_loaders(name, batch=128, size=28)
    task = info["task"]
    n_classes = len(info["label"])
    print(f"\n=== FGSM on {name} ===")
    model = build_model("resnet18", n_classes, pretrained=True)
    train_short(model, loaders, task, epochs=3, lr=1e-3)
    model.eval()
    loss_fn = get_loss_fn(task)

    for eps in EPS_LIST:
        correct = 0; total = 0
        all_probs, all_labs = [], []
        for x, y in loaders["test"]:
            x = x.to(DEVICE); x.requires_grad_(True)
            if task == "multi-label, binary-class":
                y_t = torch.tensor(y, dtype=torch.float32, device=DEVICE)
            else:
                y_t = torch.tensor(np.asarray(y).reshape(-1), dtype=torch.long, device=DEVICE)

            if eps > 0:
                logits = model(x)
                loss = loss_fn(logits, y_t)
                model.zero_grad()
                loss.backward()
                x_adv = (x + eps * x.grad.sign()).detach().clamp(-3.0, 3.0)
            else:
                x_adv = x.detach()

            with torch.no_grad():
                logits2 = model(x_adv)
                if task == "multi-label, binary-class":
                    probs = torch.sigmoid(logits2).cpu().numpy()
                    preds = (probs >= 0.5).astype(np.int32)
                    y_np = np.asarray(y).astype(np.int32)
                    correct += int((preds == y_np).all(axis=1).sum())
                    total += preds.shape[0]
                    all_probs.append(probs); all_labs.append(y_np)
                else:
                    probs = torch.softmax(logits2, 1).cpu().numpy()
                    preds = probs.argmax(1)
                    y_np = np.asarray(y).astype(np.int64).reshape(-1)
                    correct += int((preds == y_np).sum())
                    total += preds.shape[0]
                    all_probs.append(probs); all_labs.append(y_np)

        acc = correct / max(1, total)
        # AUC
        P = np.concatenate(all_probs, 0); Y = np.concatenate(all_labs, 0)
        try:
            if task == "multi-label, binary-class":
                aucs = [roc_auc_score(Y[:, i], P[:, i]) for i in range(Y.shape[1]) if len(np.unique(Y[:, i])) >= 2]
                auc = float(np.mean(aucs))
            else:
                auc = float(roc_auc_score(Y, P, multi_class="ovr", average="macro"))
        except Exception:
            auc = float("nan")
        row = {"dataset": name, "epsilon": eps, "accuracy": round(acc, 4), "macro_auc": round(auc, 4)}
        print(row)
        rows.append(row)

df = pd.DataFrame(rows)
save_csv(df, "adv_fgsm.csv")
emit_result("acc_drop_eps0.1",
            f"{(df[df['epsilon']==0.0]['accuracy'].mean() - df[df['epsilon']==0.1]['accuracy'].mean()):.4f}")
