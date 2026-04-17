"""MIQA v2 · Ultrassom Mama com BUSI Dataset (Kaggle).

Dataset: aryashah2k/breast-ultrasound-images-dataset
- Classes: benign, malignant, normal
- 780 imagens originais + GT masks (ignoramos masks)

Arquitetura: EfficientNet-B0 pretrained, augmentation intensa (data augmentation
agressiva em dataset pequeno). Usa class_weights pra balancear.

Output: miqa_kaggle_us_results.csv + summary.json
"""
import os
import time
import glob
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torchvision import models, transforms
from PIL import Image
from sklearn.metrics import roc_auc_score, f1_score, accuracy_score

from _utils import EXP_DIR, DEVICE, set_seed, emit_result, save_csv, save_json

set_seed(42)

DATA_ROOT = os.environ.get(
    "MIQA_BUSI_ROOT",
    "/home/oftalmousp/jv-teste/miqa_backend/kaggle_datasets/busi/Dataset_BUSI_with_GT",
)
CLASSES = ["benign", "malignant", "normal"]
BATCH = 32
EPOCHS = 20
LR = 3e-4
IMG_SIZE = 224


class BUSI(Dataset):
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
        # BUSI usa maiuscula inicial (Benign/Malignant/Normal)
        patterns = [os.path.join(DATA_ROOT, cname.capitalize(), "*).png"),
                    os.path.join(DATA_ROOT, cname, "*).png"),
                    os.path.join(DATA_ROOT, cname.capitalize(), f"{cname} (*).png"),
                    os.path.join(DATA_ROOT, cname, f"{cname} (*).png")]
        files = []
        for p in patterns:
            files.extend(glob.glob(p))
        # remove mask files (terminam com _mask.png)
        files = [f for f in files if "_mask" not in f.lower()]
        files = list(set(files))
        print(f"  {cname}: {len(files)} imagens")
        items.extend([(f, cidx) for f in files])
    return items


def train_one_epoch(model, dl, opt, loss_fn):
    model.train()
    tl = 0; n = 0
    for x, y in dl:
        x = x.to(DEVICE); y = y.to(DEVICE)
        logits = model(x)
        loss = loss_fn(logits, y)
        opt.zero_grad(); loss.backward(); opt.step()
        tl += float(loss.item()) * x.size(0); n += x.size(0)
    return tl / max(1, n)


@torch.no_grad()
def evaluate(model, dl):
    model.eval()
    probs, labs = [], []
    for x, y in dl:
        probs.append(torch.softmax(model(x.to(DEVICE)), 1).cpu().numpy())
        labs.append(y.numpy())
    P = np.concatenate(probs); Y = np.concatenate(labs)
    preds = P.argmax(1)
    acc = accuracy_score(Y, preds)
    f1 = f1_score(Y, preds, average="macro", zero_division=0)
    try:
        auc = roc_auc_score(Y, P, multi_class="ovr", average="macro")
    except Exception:
        auc = float("nan")
    per_class_acc = {cn: float((preds[Y==ci] == ci).mean()) if (Y==ci).any() else None
                     for ci, cn in enumerate(CLASSES)}
    return {"acc": float(acc), "f1": float(f1), "auc": float(auc),
            "per_class_acc": per_class_acc}


def main():
    t0 = time.time()
    if not os.path.exists(DATA_ROOT):
        print(f"DATA_ROOT nao existe: {DATA_ROOT}")
        emit_result("status", "dataset_missing")
        return
    items = build_samples()
    print(f"total={len(items)}")
    if len(items) < 100:
        emit_result("status", "too_few_images")
        return

    rng = np.random.default_rng(42)
    rng.shuffle(items)
    n = len(items)
    n_train = int(0.7*n); n_val = int(0.15*n)
    train_items = items[:n_train]; val_items = items[n_train:n_train+n_val]
    test_items = items[n_train+n_val:]

    # Class weights (BUSI tem desbalanceamento forte)
    class_counts = np.bincount([y for _, y in train_items], minlength=len(CLASSES))
    class_weights = torch.tensor(
        class_counts.sum() / (len(CLASSES) * (class_counts + 1e-6)),
        dtype=torch.float32,
    ).to(DEVICE)
    print(f"class counts train: {class_counts.tolist()}")
    print(f"class weights: {class_weights.cpu().numpy()}")

    T_train = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.15, contrast=0.15),
        transforms.RandomAffine(0, translate=(0.05, 0.05)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    T_eval = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    dl_train = DataLoader(BUSI(train_items, T_train), batch_size=BATCH, shuffle=True,
                          num_workers=4, pin_memory=True, drop_last=True)
    dl_val = DataLoader(BUSI(val_items, T_eval), batch_size=BATCH, shuffle=False,
                        num_workers=2, pin_memory=True)
    dl_test = DataLoader(BUSI(test_items, T_eval), batch_size=BATCH, shuffle=False,
                         num_workers=2, pin_memory=True)

    model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.DEFAULT)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(CLASSES))
    model = model.to(DEVICE)

    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=EPOCHS)
    loss_fn = nn.CrossEntropyLoss(weight=class_weights, label_smoothing=0.1)

    best_auc = 0.0
    for ep in range(EPOCHS):
        tl = train_one_epoch(model, dl_train, opt, loss_fn)
        val = evaluate(model, dl_val)
        sched.step()
        print(f"ep {ep+1}/{EPOCHS}  train_loss={tl:.4f}  val_acc={val['acc']:.4f}  val_auc={val['auc']:.4f}")
        if val["auc"] > best_auc:
            best_auc = val["auc"]
            torch.save(model.state_dict(), f"{EXP_DIR}/miqa_kaggle_us_best.pt")

    model.load_state_dict(torch.load(f"{EXP_DIR}/miqa_kaggle_us_best.pt"))
    test = evaluate(model, dl_test)
    print(f"\nTEST  acc={test['acc']:.4f}  f1={test['f1']:.4f}  auc={test['auc']:.4f}")
    print(f"per-class acc: {test['per_class_acc']}")

    save_csv(pd.DataFrame([{"class": cn, "acc": test["per_class_acc"][cn]} for cn in CLASSES]),
             "miqa_kaggle_us_per_class.csv")
    save_json({
        "dataset": "BUSI - Breast Ultrasound Images (Kaggle)",
        "arch": "EfficientNet-B0 pretrained + class weights + label smoothing",
        "epochs": EPOCHS, "batch": BATCH, "img_size": IMG_SIZE, "lr": LR,
        "n_train": len(train_items), "n_val": len(val_items), "n_test": len(test_items),
        "test_acc": test["acc"], "test_f1": test["f1"], "test_auc": test["auc"],
        "best_val_auc": best_auc,
        "per_class_acc": test["per_class_acc"],
        "classes": CLASSES,
        "class_weights": class_weights.cpu().numpy().tolist(),
        "seconds": time.time() - t0,
    }, "miqa_kaggle_us_summary.json")

    emit_result("test_auc", f"{test['auc']:.4f}")
    emit_result("test_acc", f"{test['acc']:.4f}")
    emit_result("test_f1", f"{test['f1']:.4f}")
    emit_result("seconds", f"{time.time()-t0:.1f}")


if __name__ == "__main__":
    main()
