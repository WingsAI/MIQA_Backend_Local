"""MIQA v2 · RX Chest com COVID-19 Radiography Dataset (Kaggle).

Dataset: tawsifurrahman/covid19-radiography-database
- Classes: COVID, Lung_Opacity, Normal, Viral Pneumonia
- ~21k images, 299x299 PNG

Arquitetura: ResNet50 ImageNet pretrained + fine-tune, augmentation padrao.
Output: miqa_kaggle_rx_results.csv + summary.json
"""
import os
import time
import glob
import pathlib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader, random_split
from torchvision import models, transforms
from PIL import Image
from sklearn.metrics import roc_auc_score, classification_report, f1_score, accuracy_score

from _utils import EXP_DIR, DEVICE, set_seed, emit_result, save_csv, save_json

set_seed(42)

DATA_ROOT = os.environ.get(
    "MIQA_COVID_ROOT",
    "/home/oftalmousp/jv-teste/miqa_backend/kaggle_datasets/covid_radiography/COVID-19_Radiography_Dataset",
)
CLASSES = ["COVID", "Lung_Opacity", "Normal", "Viral Pneumonia"]
BATCH = 64
EPOCHS = 8
LR = 1e-4
IMG_SIZE = 224


class CovidChestXRay(Dataset):
    def __init__(self, samples, transform):
        self.samples = samples
        self.transform = transform
    def __len__(self): return len(self.samples)
    def __getitem__(self, i):
        path, label = self.samples[i]
        img = Image.open(path).convert("RGB")
        return self.transform(img), label


def build_samples():
    items = []
    for cidx, cname in enumerate(CLASSES):
        pattern = os.path.join(DATA_ROOT, cname, "images", "*.png")
        files = glob.glob(pattern)
        if not files:
            pattern = os.path.join(DATA_ROOT, cname, "*.png")
            files = glob.glob(pattern)
        print(f"  {cname}: {len(files)} imagens")
        items.extend([(f, cidx) for f in files])
    return items


def train_one_epoch(model, dl, opt, loss_fn):
    model.train()
    tl = 0; n = 0
    for x, y in dl:
        x = x.to(DEVICE, non_blocking=True); y = y.to(DEVICE)
        logits = model(x)
        loss = loss_fn(logits, y)
        opt.zero_grad(); loss.backward(); opt.step()
        tl += float(loss.item()) * x.size(0); n += x.size(0)
    return tl / max(1, n)


@torch.no_grad()
def evaluate(model, dl):
    model.eval()
    all_probs, all_y = [], []
    for x, y in dl:
        x = x.to(DEVICE)
        logits = model(x)
        all_probs.append(torch.softmax(logits, 1).cpu().numpy())
        all_y.append(y.numpy())
    P = np.concatenate(all_probs); Y = np.concatenate(all_y)
    preds = P.argmax(1)
    acc = accuracy_score(Y, preds)
    f1 = f1_score(Y, preds, average="macro", zero_division=0)
    try:
        auc = roc_auc_score(Y, P, multi_class="ovr", average="macro")
    except Exception:
        auc = float("nan")
    per_class_acc = {}
    for ci, cn in enumerate(CLASSES):
        mask = Y == ci
        per_class_acc[cn] = float((preds[mask] == ci).mean()) if mask.any() else None
    return {"acc": float(acc), "f1": float(f1), "auc": float(auc),
            "per_class_acc": per_class_acc, "probs": P, "labels": Y, "preds": preds}


def main():
    t0 = time.time()
    if not os.path.exists(DATA_ROOT):
        print(f"DATA_ROOT nao existe: {DATA_ROOT}")
        emit_result("status", "dataset_missing")
        return
    items = build_samples()
    print(f"total={len(items)}")
    if len(items) < 500:
        emit_result("status", "too_few_images")
        return

    # 70/15/15 split
    tv_train = [(p, y) for p, y in items]
    rng = np.random.default_rng(42)
    rng.shuffle(tv_train)
    n = len(tv_train)
    n_train = int(0.7 * n); n_val = int(0.15 * n)
    train_items = tv_train[:n_train]
    val_items = tv_train[n_train:n_train+n_val]
    test_items = tv_train[n_train+n_val:]

    T_train = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(10),
        transforms.ColorJitter(brightness=0.1, contrast=0.1),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    T_eval = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    dl_train = DataLoader(CovidChestXRay(train_items, T_train), batch_size=BATCH,
                          shuffle=True, num_workers=4, pin_memory=True, drop_last=True)
    dl_val = DataLoader(CovidChestXRay(val_items, T_eval), batch_size=BATCH,
                        shuffle=False, num_workers=4, pin_memory=True)
    dl_test = DataLoader(CovidChestXRay(test_items, T_eval), batch_size=BATCH,
                         shuffle=False, num_workers=4, pin_memory=True)

    # ResNet50 pretrained
    model = models.resnet50(weights=models.ResNet50_Weights.DEFAULT)
    model.fc = nn.Linear(model.fc.in_features, len(CLASSES))
    model = model.to(DEVICE)

    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=EPOCHS)
    loss_fn = nn.CrossEntropyLoss()

    best_auc = 0.0
    for ep in range(EPOCHS):
        tl = train_one_epoch(model, dl_train, opt, loss_fn)
        val = evaluate(model, dl_val)
        sched.step()
        print(f"ep {ep+1}/{EPOCHS}  train_loss={tl:.4f}  val_acc={val['acc']:.4f}  val_auc={val['auc']:.4f}")
        if val["auc"] > best_auc:
            best_auc = val["auc"]
            torch.save(model.state_dict(), f"{EXP_DIR}/miqa_kaggle_rx_best.pt")

    # Reload best + eval test
    model.load_state_dict(torch.load(f"{EXP_DIR}/miqa_kaggle_rx_best.pt"))
    test = evaluate(model, dl_test)
    print(f"\nTEST  acc={test['acc']:.4f}  f1={test['f1']:.4f}  auc={test['auc']:.4f}")

    # Save results
    per_class_rows = [{"class": cn, "acc": test["per_class_acc"][cn]} for cn in CLASSES]
    save_csv(pd.DataFrame(per_class_rows), "miqa_kaggle_rx_per_class.csv")

    save_json({
        "dataset": "COVID-19 Radiography (Kaggle)",
        "arch": "ResNet50 pretrained ImageNet",
        "epochs": EPOCHS, "batch": BATCH, "img_size": IMG_SIZE,
        "n_train": len(train_items), "n_val": len(val_items), "n_test": len(test_items),
        "test_acc": test["acc"], "test_f1": test["f1"], "test_auc": test["auc"],
        "best_val_auc": best_auc,
        "per_class_acc": test["per_class_acc"],
        "classes": CLASSES,
        "seconds": time.time() - t0,
    }, "miqa_kaggle_rx_summary.json")

    emit_result("test_auc", f"{test['auc']:.4f}")
    emit_result("test_acc", f"{test['acc']:.4f}")
    emit_result("best_val_auc", f"{best_auc:.4f}")
    emit_result("seconds", f"{time.time()-t0:.1f}")


if __name__ == "__main__":
    main()
