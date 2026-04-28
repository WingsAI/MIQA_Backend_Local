"""Task 17 — Feature extraction ResNet18 ImageNet-pretrained (sem fine-tune), 512-d embeddings.

Output: features_resnet18.npz  { chestmnist, breastmnist, organamnist, and corresponding *_labels }
        features_resnet18_meta.json  (shapes + label counts)
"""
import torch
import numpy as np
import torchvision.models as tvm
from torch.utils.data import DataLoader
from _utils import (set_seed, get_dataset, DEVICE, EXP_DIR,
                    extract_resnet18_features, save_json, emit_result)

set_seed(42)
backbone = tvm.resnet18(weights=tvm.ResNet18_Weights.DEFAULT).to(DEVICE).eval()

bundles = {}
meta = {}
for name in ["chestmnist", "breastmnist", "organamnist"]:
    # use train+val+test para ter embeddings de todos splits
    feats_all, labs_all = [], []
    for split in ["train", "val", "test"]:
        ds, info = get_dataset(name, split=split, size=28)
        dl = DataLoader(ds, batch_size=256, shuffle=False, num_workers=0, pin_memory=True)
        with torch.no_grad():
            for x, y in dl:
                x = x.to(DEVICE)
                f = extract_resnet18_features(backbone, x).cpu().numpy()
                feats_all.append(f)
                labs_all.append(np.asarray(y))
    F = np.concatenate(feats_all, 0).astype(np.float32)
    L = np.concatenate(labs_all, 0)
    bundles[f"{name}_feats"] = F
    bundles[f"{name}_labels"] = L
    meta[name] = {"shape": list(F.shape), "labels_shape": list(L.shape), "task": info["task"]}
    print(f"{name:13s} feats={F.shape}  labels={L.shape}")

np.savez_compressed(f"{EXP_DIR}/features_resnet18.npz", **bundles)
print(f"SAVED: {EXP_DIR}/features_resnet18.npz")
save_json(meta, "features_resnet18_meta.json")
emit_result("total_samples", int(sum(v["shape"][0] for v in meta.values())))
