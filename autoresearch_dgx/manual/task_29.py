"""Task 29 — Grad-CAM samples de ResNet18 em OrganAMNIST.

Output: gradcam_samples.png  (grid 4x4 original / heatmap / overlay)
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch
import torch.nn as nn
import torch.nn.functional as F
from _utils import (set_seed, quick_loaders, build_model, train_short, DEVICE,
                    EXP_DIR, emit_result)

set_seed(42)
NAME = "organamnist"
loaders, info = quick_loaders(NAME, batch=128, size=28)
task = info["task"]
n_classes = len(info["label"])
print(f"=== Grad-CAM on {NAME} ===")
model = build_model("resnet18", n_classes, pretrained=True)
train_short(model, loaders, task, epochs=3, lr=1e-3)
model = model.to(DEVICE).eval()

# hook para ultima conv (layer4[-1].conv2)
target_layer = model.layer4[-1].conv2
activations = {}; gradients = {}
def fwd_hook(m, i, o): activations["v"] = o
def bwd_hook(m, gi, go): gradients["v"] = go[0]
h1 = target_layer.register_forward_hook(fwd_hook)
h2 = target_layer.register_full_backward_hook(bwd_hook)

# pegar um batch do test
x, y = next(iter(loaders["test"]))
x = x[:16].to(DEVICE); y_np = np.asarray(y[:16]).astype(np.int64).reshape(-1)

logits = model(x)
preds = logits.argmax(1)
scores = logits.gather(1, preds.view(-1, 1)).squeeze()
model.zero_grad()
scores.sum().backward()

grads = gradients["v"]        # [N, C, h, w]
acts = activations["v"]
weights = grads.mean(dim=(2, 3), keepdim=True)       # GAP dos gradients
cam = F.relu((weights * acts).sum(dim=1))            # [N, h, w]
# upsample p/ 28x28
cam = F.interpolate(cam.unsqueeze(1), size=(28, 28), mode="bilinear", align_corners=False).squeeze(1)
cam_np = cam.detach().cpu().numpy()
# normalize 0..1 per-image
cam_np = (cam_np - cam_np.min(axis=(1, 2), keepdims=True)) / \
         (cam_np.max(axis=(1, 2), keepdims=True) - cam_np.min(axis=(1, 2), keepdims=True) + 1e-8)

# denormalize para visualizar: invertemos normalize ImageNet
mean = np.array([0.485, 0.456, 0.406])[:, None, None]
std = np.array([0.229, 0.224, 0.225])[:, None, None]
x_np = x.detach().cpu().numpy() * std + mean
x_np = np.clip(x_np, 0, 1).transpose(0, 2, 3, 1)

# Grid 4x4 * 3 panels (orig, cam, overlay)
fig, axs = plt.subplots(4, 12, figsize=(24, 8))
label_names = info["label"]
for i in range(16):
    r, c = i // 4, (i % 4) * 3
    ax0, ax1, ax2 = axs[r, c], axs[r, c+1], axs[r, c+2]
    ax0.imshow(x_np[i]); ax0.set_title(f"true:{label_names[str(y_np[i])]}\npred:{label_names[str(int(preds[i].item()))]}", fontsize=7)
    ax1.imshow(cam_np[i], cmap="jet")
    ax2.imshow(x_np[i])
    ax2.imshow(cam_np[i], cmap="jet", alpha=0.45)
    for a in (ax0, ax1, ax2): a.set_xticks([]); a.set_yticks([])
fig.suptitle(f"Grad-CAM samples — {NAME} (ResNet18)", fontsize=12)
fig.tight_layout()
outpath = f"{EXP_DIR}/gradcam_samples.png"
fig.savefig(outpath, dpi=120)
plt.close(fig)
print(f"SAVED: {outpath}")

h1.remove(); h2.remove()
emit_result("accuracy_sample", f"{(preds.cpu().numpy() == y_np).mean():.4f}")
