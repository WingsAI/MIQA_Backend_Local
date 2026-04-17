"""Task 27 — Knowledge distillation.
Teacher: ResNet18 pretrained (3 epocas).
Student: MobileNetV3-Small (3 epocas alone vs 3 epocas com KD loss).

Output: distillation.csv  [dataset, mode, macro_auc, params, compression_ratio_vs_teacher]
"""
import time
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from _utils import (set_seed, quick_loaders, build_model, evaluate, train_short,
                    DEVICE, save_csv, emit_result, count_params, get_loss_fn)

set_seed(42)
DATASETS = ["breastmnist", "organamnist"]
T = 4.0  # temperature
ALPHA = 0.7
EPOCHS = 3
rows = []

for name in DATASETS:
    loaders, info = quick_loaders(name, batch=128, size=28)
    task = info["task"]
    n_classes = len(info["label"])
    print(f"\n### Dataset: {name} ###")

    # 1) treinar teacher
    print("[teacher] ResNet18 pretrained")
    teacher = build_model("resnet18", n_classes, pretrained=True)
    train_short(teacher, loaders, task, epochs=EPOCHS, lr=1e-3)
    teacher.eval()
    t_params = count_params(teacher)

    # 2) student alone
    print("[student alone] MobileNetV3-Small")
    set_seed(42)
    student_alone = build_model("mobilenet_v3_small", n_classes, pretrained=True)
    train_short(student_alone, loaders, task, epochs=EPOCHS, lr=1e-3)
    res_alone = evaluate(student_alone, loaders["test"], task)
    s_params = count_params(student_alone)

    # 3) student com KD
    print("[student KD] MobileNetV3-Small + teacher soft targets")
    set_seed(42)
    student_kd = build_model("mobilenet_v3_small", n_classes, pretrained=True).to(DEVICE)
    opt = torch.optim.AdamW(student_kd.parameters(), lr=1e-3, weight_decay=1e-4)
    hard_loss_fn = get_loss_fn(task)

    for ep in range(EPOCHS):
        student_kd.train()
        for x, y in loaders["train"]:
            x = x.to(DEVICE)
            if task == "multi-label, binary-class":
                y_t = torch.tensor(y, dtype=torch.float32, device=DEVICE)
            else:
                y_t = torch.tensor(np.asarray(y).reshape(-1), dtype=torch.long, device=DEVICE)
            with torch.no_grad():
                t_logits = teacher(x)
            s_logits = student_kd(x)
            hard_loss = hard_loss_fn(s_logits, y_t)
            if task == "multi-label, binary-class":
                soft_t = torch.sigmoid(t_logits / T)
                soft_s = torch.sigmoid(s_logits / T)
                soft_loss = F.mse_loss(soft_s, soft_t)
            else:
                soft_loss = F.kl_div(
                    F.log_softmax(s_logits / T, dim=1),
                    F.softmax(t_logits / T, dim=1),
                    reduction="batchmean"
                ) * (T * T)
            loss = ALPHA * soft_loss + (1 - ALPHA) * hard_loss
            opt.zero_grad(); loss.backward(); opt.step()

    res_kd = evaluate(student_kd, loaders["test"], task)

    rows += [
        {"dataset": name, "mode": "teacher_resnet18",
         "macro_auc": round(evaluate(teacher, loaders["test"], task)["macro_auc"], 4),
         "params": t_params, "compression_ratio": 1.0},
        {"dataset": name, "mode": "student_alone",
         "macro_auc": round(res_alone["macro_auc"], 4),
         "params": s_params, "compression_ratio": round(t_params / s_params, 2)},
        {"dataset": name, "mode": "student_kd",
         "macro_auc": round(res_kd["macro_auc"], 4),
         "params": s_params, "compression_ratio": round(t_params / s_params, 2)},
    ]
    for r in rows[-3:]: print(r)

df = pd.DataFrame(rows)
save_csv(df, "distillation.csv")
# kd gain por dataset
piv = df.pivot(index="dataset", columns="mode", values="macro_auc")
emit_result("mean_kd_gain", f"{(piv['student_kd'] - piv['student_alone']).mean():.4f}")
