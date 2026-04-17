"""Task 16 — Benchmark 3x3: {ChestMNIST, BreastMNIST, OrganAMNIST} x {ResNet18, EfficientNet-B0, MobileNetV3-Small}, 3 epocas.

Output: benchmark_3x3.csv  [dataset, arch, task, n_classes, macro_auc, accuracy, macro_f1, params, seconds]
"""
import pandas as pd
from _utils import (set_seed, quick_loaders, build_model, train_short,
                    evaluate, save_csv, emit_result, count_params)

set_seed(42)
DATASETS = ["chestmnist", "breastmnist", "organamnist"]
ARCHS = ["resnet18", "efficientnet_b0", "mobilenet_v3_small"]

rows = []
for ds_name in DATASETS:
    loaders, info = quick_loaders(ds_name, batch=128, size=28)
    task = info["task"]
    n_classes = len(info["label"])
    for arch in ARCHS:
        print(f"\n=== {ds_name} x {arch} ===")
        set_seed(42)
        model = build_model(arch, n_classes, pretrained=True)
        seconds = train_short(model, loaders, task, epochs=3, lr=1e-3)
        res = evaluate(model, loaders["test"], task)
        row = {
            "dataset": ds_name, "arch": arch, "task": task, "n_classes": n_classes,
            "macro_auc": round(res["macro_auc"], 4),
            "accuracy": round(res["accuracy"], 4),
            "macro_f1": round(res["macro_f1"], 4),
            "params": count_params(model),
            "seconds": round(seconds, 1),
        }
        print(row)
        rows.append(row)

df = pd.DataFrame(rows)
save_csv(df, "benchmark_3x3.csv")
emit_result("mean_macro_auc", f"{df['macro_auc'].mean():.4f}")
emit_result("best_combo", f"{df.loc[df['macro_auc'].idxmax(), 'dataset']}/{df.loc[df['macro_auc'].idxmax(), 'arch']}")
