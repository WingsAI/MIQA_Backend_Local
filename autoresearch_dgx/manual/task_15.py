"""Task 15 — ResNet18 pretrained ImageNet em ChestMNIST (5 epocas), AUC por label.

Output: chestmnist_resnet18.csv  [label_idx, label_name, auc]
        chestmnist_resnet18_summary.json  { macro_auc, accuracy, macro_f1, epochs, seconds }
"""
import time
import pandas as pd
from _utils import (set_seed, quick_loaders, build_model, train_short,
                    evaluate, save_csv, save_json, emit_result)

set_seed(42)
loaders, info = quick_loaders("chestmnist", batch=128, size=28)
task = info["task"]
num_classes = len(info["label"])
print(f"chestmnist | task={task} | n_classes={num_classes}")

model = build_model("resnet18", num_classes, pretrained=True)
seconds = train_short(model, loaders, task, epochs=5, lr=1e-3)

res = evaluate(model, loaders["test"], task)
print(f"macro_auc={res['macro_auc']:.4f} acc={res['accuracy']:.4f} f1={res['macro_f1']:.4f}")

rows = []
for i, name in info["label"].items():
    rows.append({"label_idx": int(i), "label_name": name, "auc": res["per_label_auc"][int(i)]})
df = pd.DataFrame(rows).sort_values("auc", ascending=False)
save_csv(df, "chestmnist_resnet18.csv")

save_json({
    "dataset": "chestmnist", "arch": "resnet18", "pretrained": True, "epochs": 5,
    "macro_auc": res["macro_auc"], "accuracy": res["accuracy"], "macro_f1": res["macro_f1"],
    "seconds": seconds, "per_label_auc": res["per_label_auc"],
}, "chestmnist_resnet18_summary.json")

emit_result("macro_auc", f"{res['macro_auc']:.4f}")
emit_result("seconds", f"{seconds:.1f}")
