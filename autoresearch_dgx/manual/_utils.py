"""MIQA Autoresearch — shared utilities (manual scripts, replaces Gemma4 generation)
MedMNIST v2 API, seed 42, output to gemma4_experiments/ for compatibility with existing log viewers.
"""
import os
import time
import json
import random
import numpy as np
import torch
import torch.nn as nn
import torchvision.models as tvm
import torchvision.transforms as T
from torch.utils.data import DataLoader, Dataset, Subset
from medmnist import INFO, ChestMNIST, BreastMNIST, OrganAMNIST

SEED = 42
EXP_DIR = os.environ.get(
    "MIQA_EXP_DIR",
    "/home/oftalmousp/jv-teste/miqa_backend/autoresearch/gemma4_experiments",
)
os.makedirs(EXP_DIR, exist_ok=True)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

DATASET_CLASSES = {
    "chestmnist": ChestMNIST,
    "breastmnist": BreastMNIST,
    "organamnist": OrganAMNIST,
}

# default channel means/stds: MedMNIST is grayscale but we convert to RGB (as_rgb=True) for pretrained nets
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def set_seed(seed: int = SEED):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def get_dataset(name: str, split: str = "train", size: int = 28, as_rgb: bool = True,
                normalize: bool = True, augment: bool = False):
    """Load a MedMNIST v2 dataset with standard transforms.

    Returns: (dataset, info_dict). dataset[i] -> (tensor[C,H,W], label_np).
    """
    cls = DATASET_CLASSES[name]
    info = INFO[name]

    tlist = []
    if augment and split == "train":
        tlist += [T.RandomHorizontalFlip(), T.RandomRotation(10)]
    tlist.append(T.ToTensor())
    if normalize:
        if as_rgb:
            tlist.append(T.Normalize(IMAGENET_MEAN, IMAGENET_STD))
        else:
            tlist.append(T.Normalize([0.5], [0.5]))
    transform = T.Compose(tlist)

    ds = cls(split=split, download=True, size=size, as_rgb=as_rgb, transform=transform)
    return ds, info


def label_to_tensor(labels, task: str) -> torch.Tensor:
    """Convert MedMNIST labels to proper tensor shape for loss computation."""
    if task in ("multi-label, binary-class",):
        arr = np.asarray(labels, dtype=np.float32)
        return torch.from_numpy(arr)
    # multi-class / binary-class: labels is shape [N,1]
    lab = np.asarray(labels).astype(np.int64).reshape(-1)
    return torch.from_numpy(lab)


def build_model(arch: str, num_classes: int, pretrained: bool = True) -> nn.Module:
    """Build a torchvision backbone with replaced classifier head."""
    if arch == "resnet18":
        w = tvm.ResNet18_Weights.DEFAULT if pretrained else None
        m = tvm.resnet18(weights=w)
        m.fc = nn.Linear(m.fc.in_features, num_classes)
    elif arch == "efficientnet_b0":
        w = tvm.EfficientNet_B0_Weights.DEFAULT if pretrained else None
        m = tvm.efficientnet_b0(weights=w)
        m.classifier[1] = nn.Linear(m.classifier[1].in_features, num_classes)
    elif arch == "mobilenet_v3_small":
        w = tvm.MobileNet_V3_Small_Weights.DEFAULT if pretrained else None
        m = tvm.mobilenet_v3_small(weights=w)
        m.classifier[3] = nn.Linear(m.classifier[3].in_features, num_classes)
    else:
        raise ValueError(f"unknown arch: {arch}")
    return m


def extract_resnet18_features(backbone: nn.Module, x: torch.Tensor) -> torch.Tensor:
    """Pass x through a resnet18 up to global avgpool (returns [N,512])."""
    b = backbone
    x = b.conv1(x); x = b.bn1(x); x = b.relu(x); x = b.maxpool(x)
    x = b.layer1(x); x = b.layer2(x); x = b.layer3(x); x = b.layer4(x)
    x = b.avgpool(x)
    return torch.flatten(x, 1)


def train_one_epoch(model, loader, optimizer, loss_fn, task: str):
    model.train()
    total, running = 0, 0.0
    for x, y in loader:
        x = x.to(DEVICE, non_blocking=True)
        y_t = label_to_tensor(y, task).to(DEVICE, non_blocking=True)
        logits = model(x)
        if task == "multi-label, binary-class":
            loss = loss_fn(logits, y_t)
        else:
            loss = loss_fn(logits, y_t)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        running += float(loss.item()) * x.size(0)
        total += x.size(0)
    return running / max(1, total)


@torch.no_grad()
def evaluate(model, loader, task: str):
    """Return dict with probs/labels/metrics. AUC per class + macro AUC + accuracy."""
    from sklearn.metrics import roc_auc_score, accuracy_score, f1_score
    model.eval()
    all_logits, all_y = [], []
    for x, y in loader:
        x = x.to(DEVICE)
        logits = model(x)
        all_logits.append(logits.cpu())
        all_y.append(torch.as_tensor(y))
    logits = torch.cat(all_logits, 0)
    y = torch.cat(all_y, 0)

    out = {"task": task}
    if task == "multi-label, binary-class":
        probs = torch.sigmoid(logits).numpy()
        y_np = y.numpy().astype(np.float32)
        aucs = []
        for i in range(y_np.shape[1]):
            if len(np.unique(y_np[:, i])) < 2:
                aucs.append(float("nan")); continue
            aucs.append(roc_auc_score(y_np[:, i], probs[:, i]))
        out["per_label_auc"] = aucs
        out["macro_auc"] = float(np.nanmean(aucs))
        preds = (probs >= 0.5).astype(np.int32)
        out["macro_f1"] = float(f1_score(y_np, preds, average="macro", zero_division=0))
        out["accuracy"] = float((preds == y_np).all(axis=1).mean())
        out["probs"] = probs
        out["labels"] = y_np
    else:  # multi-class (or binary-class 2-way)
        probs = torch.softmax(logits, dim=1).numpy()
        y_np = y.numpy().astype(np.int64).reshape(-1)
        n_classes = probs.shape[1]
        try:
            if n_classes == 2:
                out["macro_auc"] = float(roc_auc_score(y_np, probs[:, 1]))
            else:
                out["macro_auc"] = float(roc_auc_score(y_np, probs, multi_class="ovr", average="macro"))
        except Exception as e:
            print(f"auc error: {e}")
            out["macro_auc"] = float("nan")
        preds = probs.argmax(axis=1)
        out["accuracy"] = float(accuracy_score(y_np, preds))
        out["macro_f1"] = float(f1_score(y_np, preds, average="macro", zero_division=0))
        out["probs"] = probs
        out["labels"] = y_np
    return out


def get_loss_fn(task: str):
    if task == "multi-label, binary-class":
        return nn.BCEWithLogitsLoss()
    return nn.CrossEntropyLoss()


def save_csv(df, filename: str):
    path = os.path.join(EXP_DIR, filename)
    df.to_csv(path, index=False)
    print(f"SAVED: {path}")
    return path


def save_json(obj, filename: str):
    path = os.path.join(EXP_DIR, filename)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=str)
    print(f"SAVED: {path}")
    return path


def emit_result(key: str, value):
    """Standard marker line parsed by the summary script."""
    print(f"RESULT: {key}={value}")


def count_params(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters() if p.requires_grad)


def quick_loaders(name: str, batch: int = 128, size: int = 28, augment: bool = False,
                  workers: int = 2):
    train_ds, info = get_dataset(name, "train", size=size, augment=augment)
    val_ds, _ = get_dataset(name, "val", size=size)
    test_ds, _ = get_dataset(name, "test", size=size)
    loaders = {
        # drop_last=True fundamental — BatchNorm quebra com batch_size=1 no train
        "train": DataLoader(train_ds, batch_size=batch, shuffle=True, num_workers=workers,
                            pin_memory=True, drop_last=True),
        "val": DataLoader(val_ds, batch_size=batch, shuffle=False, num_workers=workers,
                          pin_memory=True),
        "test": DataLoader(test_ds, batch_size=batch, shuffle=False, num_workers=workers,
                           pin_memory=True),
    }
    return loaders, info


def train_short(model, loaders, task: str, epochs: int = 3, lr: float = 1e-3):
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    loss_fn = get_loss_fn(task)
    model.to(DEVICE)
    t0 = time.time()
    for ep in range(epochs):
        tl = train_one_epoch(model, loaders["train"], optimizer, loss_fn, task)
        print(f"  epoch {ep+1}/{epochs}  train_loss={tl:.4f}")
    dt = time.time() - t0
    return dt
