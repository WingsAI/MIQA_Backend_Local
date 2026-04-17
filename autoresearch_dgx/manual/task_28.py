"""Task 28 — INT8 dynamic quantization (compare size, latency, acc).
Dynamic quantization funciona bem nas camadas Linear.

Output: quantization.csv  [dataset, mode, size_mb, latency_ms_per_batch, macro_auc]
"""
import os
import time
import copy
import tempfile
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from _utils import (set_seed, quick_loaders, build_model, evaluate, train_short,
                    DEVICE, save_csv, emit_result)

set_seed(42)
DATASETS = ["breastmnist", "organamnist"]
rows = []

def model_size_mb(m):
    with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
        torch.save(m.state_dict(), f.name)
        size = os.path.getsize(f.name) / 1e6
    os.unlink(f.name)
    return size

def latency_ms(m, x_cpu, n=20):
    m.eval()
    with torch.no_grad():
        # warmup
        _ = m(x_cpu); _ = m(x_cpu)
        t0 = time.time()
        for _ in range(n):
            _ = m(x_cpu)
        return (time.time() - t0) / n * 1000

for name in DATASETS:
    loaders, info = quick_loaders(name, batch=128, size=28, workers=0)
    task = info["task"]
    print(f"\n=== {name} ===")
    model = build_model("resnet18", len(info["label"]), pretrained=True)
    train_short(model, loaders, task, epochs=3, lr=1e-3)

    # FP32 no CPU (quantization e CPU-only)
    model_cpu = copy.deepcopy(model).cpu().eval()
    # sample batch
    it = iter(loaders["test"])
    x_sample, _ = next(it)
    x_cpu = x_sample

    fp32_size = model_size_mb(model_cpu)
    fp32_lat = latency_ms(model_cpu, x_cpu)
    # avaliar em CPU
    from torch.utils.data import DataLoader
    cpu_loader = DataLoader(loaders["test"].dataset, batch_size=128, shuffle=False)
    import _utils
    orig_device = _utils.DEVICE
    _utils.DEVICE = torch.device("cpu")
    res_fp32 = evaluate(model_cpu, cpu_loader, task)

    rows.append({"dataset": name, "mode": "fp32_cpu", "size_mb": round(fp32_size, 2),
                 "latency_ms": round(fp32_lat, 2), "macro_auc": round(res_fp32["macro_auc"], 4)})
    print(rows[-1])

    # quantize dynamic — aarch64 (DGX Spark GB10) NAO tem kernels int8 do PyTorch,
    # entao o quantize_dynamic da RuntimeError "unknown architecure".
    try:
        qmodel = torch.ao.quantization.quantize_dynamic(model_cpu, {nn.Linear}, dtype=torch.qint8)
        int8_size = model_size_mb(qmodel)
        int8_lat = latency_ms(qmodel, x_cpu)
        res_int8 = evaluate(qmodel, cpu_loader, task)
        rows.append({"dataset": name, "mode": "int8_dynamic", "size_mb": round(int8_size, 2),
                     "latency_ms": round(int8_lat, 2),
                     "macro_auc": round(res_int8["macro_auc"], 4)})
        print(rows[-1])
    except Exception as e:
        print(f"[aarch64] INT8 dynamic quantization nao suportado: {type(e).__name__}: {e}")
        rows.append({"dataset": name, "mode": "int8_dynamic_UNSUPPORTED_aarch64",
                     "size_mb": None, "latency_ms": None, "macro_auc": None})
    _utils.DEVICE = orig_device

df = pd.DataFrame(rows)
save_csv(df, "quantization.csv")

# Tenta calcular compression e drop, mas com fallback se int8 nao rodou (aarch64)
if "int8_dynamic" in df["mode"].values:
    piv = df.pivot(index="dataset", columns="mode", values="size_mb")
    emit_result("mean_compression", f"{(piv['fp32_cpu'] / piv['int8_dynamic']).mean():.2f}x")
    piv_auc = df.pivot(index="dataset", columns="mode", values="macro_auc")
    emit_result("mean_auc_drop", f"{(piv_auc['fp32_cpu'] - piv_auc['int8_dynamic']).mean():.4f}")
else:
    emit_result("int8_status", "unsupported_aarch64")
    emit_result("fp32_mean_size_mb", f"{df[df['mode']=='fp32_cpu']['size_mb'].mean():.2f}")
