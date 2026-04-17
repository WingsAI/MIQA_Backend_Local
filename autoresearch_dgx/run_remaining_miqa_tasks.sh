#!/bin/bash
# ============================================================
# MIQA Backend — Rodar 16 tasks pendentes (15→30)
# DGX Spark + Gemma4 via Ollama
# Data: 16 Abril 2026
# ============================================================

set -u

PROJECT_ROOT="/home/oftalmousp/jv-teste/miqa_backend"
EXP_DIR="$PROJECT_ROOT/autoresearch/gemma4_experiments"
LOG_DIR="$PROJECT_ROOT/autoresearch/logs"
SCRIPTS_DIR="$PROJECT_ROOT/autoresearch/scripts"
TIMEOUT_SECS=600

mkdir -p "$EXP_DIR" "$LOG_DIR" "$SCRIPTS_DIR"

cd "$PROJECT_ROOT" || { echo "ERRO: PROJECT_ROOT nao existe"; exit 1; }

# Ativar venv
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "WARN: venv nao encontrado — usando python do sistema"
fi

# Instalar dependencias chave (idempotente)
pip install -q medmnist scikit-learn torch torchvision timm albumentations \
    pandas numpy seaborn matplotlib pyyaml 2>&1 | tail -5

# ============================================================
# DATA DOCS — contexto exato para o Gemma4
# ============================================================
read -r -d '' DATA_DOCS <<'EOF'
CONTEXTO MIQA BACKEND:
- MedMNIST v2 collection (images 28x28 grayscale/RGB)
- 3 datasets principais: ChestMNIST (14 labels multi-label),
  BreastMNIST (binary), OrganAMNIST (11 labels multi-class)
- Import correto:
    import medmnist
    from medmnist import ChestMNIST, BreastMNIST, OrganAMNIST
    from medmnist import INFO  # dicionario com metadados
- INFO[dataset_flag] tem: 'n_channels', 'n_samples', 'task',
  'python_class', 'label', 'url', 'MD5'
- Para carregar dataset:
    data = ChestMNIST(split='train', download=True, as_rgb=False)
    # data.imgs (np.array), data.labels (np.array)
- Saida base: /home/oftalmousp/jv-teste/miqa_backend/autoresearch/gemma4_experiments/
- IMPORTANTE: pandas >=2.0, use `pd.concat` (append removido)
- Nao usar relativas ("./data/") — sempre absoluto
- Nao usar `from IPython.display import *`
EOF

# ============================================================
# Template para invocar Gemma4 via Ollama
# ============================================================
call_gemma4() {
    local task_id="$1"
    local task_desc="$2"
    local out_script="$SCRIPTS_DIR/task_${task_id}.py"

    local prompt="Voce e um engenheiro ML senior. Gere UM script Python standalone para:

${task_desc}

${DATA_DOCS}

Regras:
1. Shebang #!/usr/bin/env python3
2. pip install no inicio se precisar de pacotes adicionais
3. Caminhos ABSOLUTOS
4. Imprima 'RESULT: <metric>=<value>' ao final
5. Salve outputs em ${EXP_DIR}/
6. Use seed=42
7. NAO imprima explicacoes — APENAS o codigo Python

Retorne APENAS o codigo Python (sem markdown fences)."

    curl -s http://localhost:11434/api/generate \
        -d "$(jq -n --arg m 'gemma4' --arg p "$prompt" \
            '{model:$m, prompt:$p, stream:false}')" \
        | jq -r '.response' \
        | sed 's/^```python$//' | sed 's/^```$//' \
        > "$out_script"

    # Auto-patcher de erros comuns
    sed -i 's|from IPython.display import.*||g' "$out_script"
    sed -i "s|log=True'|log=True)|g" "$out_script"
    sed -i 's|\.append(|\.concat([|g' "$out_script" 2>/dev/null || true

    echo "$out_script"
}

# ============================================================
# Executar task (3 tentativas)
# ============================================================
run_task() {
    local task_id="$1"
    local task_desc="$2"
    local log_file="$LOG_DIR/task_${task_id}.log"

    echo ""
    echo "=========================================="
    echo " TASK ${task_id}: ${task_desc:0:60}..."
    echo "=========================================="

    for attempt in 1 2 3; do
        echo "[Tentativa ${attempt}/3]"
        local script
        script=$(call_gemma4 "$task_id" "$task_desc")

        if timeout "$TIMEOUT_SECS" python "$script" 2>&1 | tee "$log_file" | tail -5; then
            if grep -q "RESULT:" "$log_file"; then
                echo "✅ TASK ${task_id} PASS (attempt ${attempt})"
                return 0
            fi
        fi

        echo "❌ Tentativa ${attempt} falhou"
        sleep 5
    done

    echo "🔴 TASK ${task_id} FAILED after 3 attempts — ver ${log_file}"
    return 1
}

# ============================================================
# 16 TASKS PENDENTES (15→30)
# ============================================================
declare -A TASKS=(
    [15]="Fix pipeline medmnist — rodar ChestMNIST com ResNet18 pre-treinado em ImageNet, 5 epocas, AUC por label, salvar como chestmnist_resnet18.csv"

    [16]="Benchmark 3 datasets (ChestMNIST, BreastMNIST, OrganAMNIST) com ResNet18/EfficientNet-B0/MobileNetV3 — 3 epocas cada — salvar matrix benchmark_3x3.csv"

    [17]="Feature extraction via ResNet18 pre-treinada — salvar embeddings 512d em features_resnet18.npy para os 3 datasets"

    [18]="t-SNE + UMAP dos embeddings ResNet18 — colorir por label — salvar embeddings_tsne.html e embeddings_umap.html"

    [19]="Data quality metrics — calcular SNR, contrast, Laplacian variance para cada imagem do test set — salvar image_quality.csv"

    [20]="Out-of-distribution detection — Mahalanobis distance + Energy score — treinar em ChestMNIST, testar BreastMNIST como OOD — salvar ood_auc.csv"

    [21]="Adversarial robustness — FGSM com eps=0.01,0.05,0.1 no BreastMNIST — salvar adv_fgsm.csv"

    [22]="Test-time augmentation — hflip+rotation+brightness — media de 5 predicoes — salvar tta_gains.csv vs baseline"

    [23]="MC Dropout para uncertainty — p=0.3, 50 samples — calcular entropia preditiva — salvar uncertainty.csv"

    [24]="Transfer learning — ImageNet pretrained vs from-scratch em BreastMNIST — 10 epocas cada — salvar transfer_vs_scratch.csv"

    [25]="Label smoothing (0.1) e mixup (alpha=0.2) em ChestMNIST — comparar com baseline — salvar regularization.csv"

    [26]="Focal loss vs BCE em ChestMNIST (desbalanceado) — gamma=2 — salvar focal_vs_bce.csv"

    [27]="Knowledge distillation — ResNet50 teacher para MobileNet student em OrganAMNIST — salvar distillation.csv"

    [28]="Quantization INT8 pos-treino com torch.quantization — comparar size+AUC — salvar quantization.csv"

    [29]="Grad-CAM para 10 imagens do BreastMNIST — salvar gradcam_samples.png"

    [30]="Relatorio final HTML — agregar todas metricas 15-29 — salvar miqa_final_report.html"
)

# ============================================================
# RUN
# ============================================================
echo "=========================================="
echo " MIQA Autoresearch — 16 tasks pendentes"
echo " Inicio: $(date)"
echo "=========================================="

PASS_COUNT=0
FAIL_COUNT=0
FAILED_IDS=()

# Ordenar chaves numericamente
for task_id in $(echo "${!TASKS[@]}" | tr ' ' '\n' | sort -n); do
    if run_task "$task_id" "${TASKS[$task_id]}"; then
        PASS_COUNT=$((PASS_COUNT+1))
    else
        FAIL_COUNT=$((FAIL_COUNT+1))
        FAILED_IDS+=("$task_id")
    fi
done

# ============================================================
# SUMMARY
# ============================================================
echo ""
echo "=========================================="
echo " FIM: $(date)"
echo "=========================================="
echo " PASS : $PASS_COUNT / 16"
echo " FAIL : $FAIL_COUNT / 16"
if [ ${#FAILED_IDS[@]} -gt 0 ]; then
    echo " Tasks falhadas: ${FAILED_IDS[*]}"
fi
echo "=========================================="

# Salvar summary
{
    echo "task_id,status,log_file"
    for task_id in $(echo "${!TASKS[@]}" | tr ' ' '\n' | sort -n); do
        local log="$LOG_DIR/task_${task_id}.log"
        if [ -f "$log" ] && grep -q "RESULT:" "$log"; then
            echo "${task_id},PASS,${log}"
        else
            echo "${task_id},FAIL,${log}"
        fi
    done
} > "$EXP_DIR/miqa_run_summary.csv"

echo "Summary salvo: $EXP_DIR/miqa_run_summary.csv"
