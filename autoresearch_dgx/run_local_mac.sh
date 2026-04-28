#!/bin/bash
# MIQA Autoresearch — runner local (Mac M2, MPS)
# Usage: ./run_local_mac.sh [first_task] [last_task]
#        defaults: 15 30
set -u

FIRST="${1:-15}"
LAST="${2:-30}"

ROOT="$(cd "$(dirname "$0")" && pwd)"
MANUAL_DIR="${ROOT}/manual"
EXP_DIR="${ROOT}/results_local"
LOG_DIR="${ROOT}/logs_local"
SUMMARY="${LOG_DIR}/miqa_local_summary.csv"
TIMEOUT_SECS=1800

VENV_PY="/Users/iaparamedicos/envs/dev/bin/python"
[ ! -x "$VENV_PY" ] && { echo "ERRO: venv nao encontrado em $VENV_PY"; exit 1; }

mkdir -p "$EXP_DIR" "$LOG_DIR"
cd "$MANUAL_DIR" || exit 1

export MIQA_EXP_DIR="$EXP_DIR"
export PYTORCH_ENABLE_MPS_FALLBACK=1   # ops nao suportadas em MPS caem em CPU
export MIQA_NUM_WORKERS=0              # macOS spawn + scripts sem __main__ guard

[ ! -f "$SUMMARY" ] && echo "task_id,status,seconds,result_line" > "$SUMMARY"

# Mac nao tem `timeout` por padrao; usa gtimeout (brew coreutils) se existir
TO=""
if command -v gtimeout >/dev/null 2>&1; then TO="gtimeout $TIMEOUT_SECS"
elif command -v timeout  >/dev/null 2>&1; then TO="timeout $TIMEOUT_SECS"
fi

run_task() {
    local tid="$1"
    local script="task_${tid}.py"
    [ ! -f "$script" ] && { echo "skip: $script nao existe"; return; }
    local log="${LOG_DIR}/task_${tid}.log"
    local t0=$(date +%s)
    echo "=== task ${tid} === $(date)"
    if $TO "$VENV_PY" "$script" > "$log" 2>&1; then
        local sec=$(( $(date +%s) - t0 ))
        local line=$(tail -n 1 "$log" | tr ',' ';' | tr '\n' ' ')
        echo "${tid},ok,${sec},${line}" >> "$SUMMARY"
        echo "  ok (${sec}s)"
    else
        local sec=$(( $(date +%s) - t0 ))
        echo "${tid},fail,${sec}," >> "$SUMMARY"
        echo "  FAIL — ver $log"
    fi
}

for tid in $(seq "$FIRST" "$LAST"); do
    run_task "$tid"
done

echo
echo "Resumo: $SUMMARY"
column -t -s, "$SUMMARY" 2>/dev/null || cat "$SUMMARY"
