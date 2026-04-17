#!/bin/bash
# MIQA Backend — Manual orchestrator (replaces Gemma4 code-gen)
# Usage: ./run_manual.sh [first_task] [last_task]
#        defaults: 15 30

set -u

FIRST="${1:-15}"
LAST="${2:-30}"

PROJECT_ROOT="/home/oftalmousp/jv-teste/miqa_backend"
MANUAL_DIR="${PROJECT_ROOT}/autoresearch/manual"
EXP_DIR="${PROJECT_ROOT}/autoresearch/gemma4_experiments"
LOG_DIR="${PROJECT_ROOT}/autoresearch/logs_manual"
SUMMARY="${LOG_DIR}/miqa_manual_summary.csv"
TIMEOUT_SECS=1800

mkdir -p "$EXP_DIR" "$LOG_DIR"
cd "$MANUAL_DIR" || { echo "ERRO: $MANUAL_DIR nao existe"; exit 1; }

# Ativar venv
source "${PROJECT_ROOT}/venv/bin/activate" || { echo "ERRO: venv nao encontrado"; exit 1; }
VENV_PY="${PROJECT_ROOT}/venv/bin/python"

# Deps (idempotente)
"$VENV_PY" -m pip install -q medmnist scikit-learn torch torchvision timm \
    albumentations pandas numpy seaborn matplotlib pyyaml \
    umap-learn opencv-python-headless scipy 2>&1 | tail -5

# Export MIQA_EXP_DIR para os scripts respeitarem
export MIQA_EXP_DIR="$EXP_DIR"

# Header do CSV
[ ! -f "$SUMMARY" ] && echo "task_id,status,seconds,result_line" > "$SUMMARY"

run_task() {
    local tid="$1"
    local script="task_${tid}.py"
    [ ! -f "$script" ] && echo "skip: $script nao existe";
    if [ ! -f "$script" ]; then
        echo "$tid,skip,0," >> "$SUMMARY"
        return
    fi
    local log="${LOG_DIR}/task_${tid}.log"
    echo ""
    echo "################################################################"
    echo "# TASK $tid — $(date +%H:%M:%S)"
    echo "################################################################"
    local t0=$(date +%s)
    # timeout + venv python; stderr merged into stdout in log
    if timeout "$TIMEOUT_SECS" "$VENV_PY" "$script" > "$log" 2>&1; then
        local dt=$(( $(date +%s) - t0 ))
        local result_line=$(grep -E '^RESULT:' "$log" | head -3 | tr '\n' ';' | sed 's/,/;/g' | sed 's/"//g')
        echo "OK  task $tid (${dt}s) — $result_line"
        echo "$tid,ok,$dt,\"$result_line\"" >> "$SUMMARY"
        tail -5 "$log"
    else
        local dt=$(( $(date +%s) - t0 ))
        echo "FAIL task $tid (${dt}s) — last 20 lines:"
        tail -20 "$log"
        echo "$tid,fail,$dt," >> "$SUMMARY"
    fi
}

echo "====================================="
echo "MIQA manual run — tasks $FIRST to $LAST"
echo "venv: $VENV_PY"
echo "exp:  $EXP_DIR"
echo "logs: $LOG_DIR"
echo "cuda: $("$VENV_PY" -c 'import torch;print(torch.cuda.is_available(), torch.cuda.device_count())')"
echo "====================================="

for t in $(seq "$FIRST" "$LAST"); do
    run_task "$t"
done

echo ""
echo "================================================"
echo "ALL DONE — summary at $SUMMARY"
echo "================================================"
cat "$SUMMARY"
echo ""
echo "Files produced in $EXP_DIR:"
ls -la "$EXP_DIR" | grep -v '^d' | wc -l
ls "$EXP_DIR" | sort
