"""Task 18 — t-SNE + UMAP dos embeddings de task 17 (PNG matplotlib, sem depend plotly).

Reads:  features_resnet18.npz
Output: embeddings_tsne.png, embeddings_umap.png
        embeddings_projections.npz  (2d coords para reuso futuro)
"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.manifold import TSNE
from _utils import set_seed, EXP_DIR, emit_result, save_json

set_seed(42)
npz = np.load(f"{EXP_DIR}/features_resnet18.npz")

# plot helper
def plot_panel(method_name, embeds, savepath="out.png"):
    n = len(embeds)
    fig, axs = plt.subplots(1, n, figsize=(6 * n, 5))
    if n == 1: axs = [axs]
    for ax, (title, emb, y) in zip(axs, embeds):
        if y.ndim > 1 and y.shape[1] > 1:
            color = y.sum(axis=1)  # multi-label: sum of positives
        else:
            color = np.asarray(y).reshape(-1)
        sc = ax.scatter(emb[:, 0], emb[:, 1], c=color, s=4, cmap="tab20", alpha=0.6)
        ax.set_title(f"{title}\n({method_name})")
        ax.set_xticks([]); ax.set_yticks([])
    fig.tight_layout()
    fig.savefig(savepath, dpi=120)
    plt.close(fig)
    print(f"SAVED: {savepath}")

# subsample para velocidade (max 3000 pts por dataset)
def subsample(F, L, n=3000):
    if F.shape[0] <= n:
        return F, L
    idx = np.random.RandomState(42).choice(F.shape[0], size=n, replace=False)
    return F[idx], L[idx]

# 1) t-SNE
tsne_bundles = []
tsne_coords = {}
for name in ["chestmnist", "breastmnist", "organamnist"]:
    F, L = subsample(npz[f"{name}_feats"], npz[f"{name}_labels"], n=3000)
    print(f"t-SNE {name} n={F.shape[0]}")
    proj = TSNE(n_components=2, random_state=42, init="pca",
                learning_rate="auto", perplexity=30).fit_transform(F)
    tsne_bundles.append((name, proj, L))
    tsne_coords[f"{name}_tsne"] = proj
plot_panel("t-SNE", tsne_bundles, savepath=f"{EXP_DIR}/embeddings_tsne.png")

# 2) UMAP (opcional — skip se biblioteca nao instalada)
try:
    import umap
    umap_bundles = []
    for name in ["chestmnist", "breastmnist", "organamnist"]:
        F, L = subsample(npz[f"{name}_feats"], npz[f"{name}_labels"], n=3000)
        print(f"UMAP {name}")
        proj = umap.UMAP(random_state=42, n_neighbors=15, min_dist=0.1).fit_transform(F)
        umap_bundles.append((name, proj, L))
        tsne_coords[f"{name}_umap"] = proj
    plot_panel("UMAP", umap_bundles, savepath=f"{EXP_DIR}/embeddings_umap.png")
    umap_ok = True
except ImportError:
    print("umap-learn nao instalado, pulando UMAP")
    umap_ok = False

np.savez_compressed(f"{EXP_DIR}/embeddings_projections.npz", **tsne_coords)
print(f"SAVED: {EXP_DIR}/embeddings_projections.npz")
save_json({"tsne": True, "umap": umap_ok}, "embeddings_meta.json")
emit_result("umap_ok", umap_ok)
