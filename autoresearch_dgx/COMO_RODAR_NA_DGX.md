# MIQA Autoresearch — Como Rodar na DGX

**Status**: 14/30 tasks completadas. Faltam **16 tasks (15-30)**.

#MIQA #DGX #Autoresearch #Gemma4 #Tecnologia

---

## Pre-requisitos

- Acesso SSH a DGX: `ssh -p 2222 oftalmousp@dgx.retina.ia.br`
- Ollama rodando com Gemma4 (`ollama list` deve mostrar `gemma4`)
- Tunnel cloudflared ativo

## Opcao 1 — Transferir via SCP (quando SSH estiver OK)

```bash
# Do Mac
scp -P 2222 /Users/jv/Documents/GitHub/MIQA_Backend_Local/autoresearch_dgx/run_remaining_miqa_tasks.sh \
    oftalmousp@dgx.retina.ia.br:~/jv-teste/miqa_backend/autoresearch/

# Na DGX
ssh -p 2222 oftalmousp@dgx.retina.ia.br
cd ~/jv-teste/miqa_backend/autoresearch
chmod +x run_remaining_miqa_tasks.sh
tmux new -s miqa_v2
./run_remaining_miqa_tasks.sh 2>&1 | tee run_$(date +%Y%m%d_%H%M).log
# Ctrl+B, D para detach
```

## Opcao 2 — Transferir via base64 (SSH instavel)

No Mac (gera o texto base64 pronto):
```bash
cat /tmp/miqa_script_b64.txt | pbcopy
# Agora cole na DGX dentro de:
```

Na DGX:
```bash
cd ~/jv-teste/miqa_backend/autoresearch
cat > run_miqa_b64.txt << 'PASTE_HERE'
# [COLE O CONTEUDO BASE64 AQUI]
PASTE_HERE
base64 -d run_miqa_b64.txt > run_remaining_miqa_tasks.sh
chmod +x run_remaining_miqa_tasks.sh
tmux new -s miqa_v2
./run_remaining_miqa_tasks.sh 2>&1 | tee run.log
```

## Opcao 3 — Colar heredoc inteiro (maior mas direto)

Se tmux reclamar de nesting, saia do tmux primeiro (`Ctrl+B, D`) e faca direto na shell da DGX.

```bash
cd ~/jv-teste/miqa_backend/autoresearch
cat > run_remaining_miqa_tasks.sh << 'SCRIPT_END'
# ... cole o conteudo inteiro do .sh aqui ...
SCRIPT_END
chmod +x run_remaining_miqa_tasks.sh
tmux new -s miqa_v2
./run_remaining_miqa_tasks.sh
```

## O que o Script Faz

1. Ativa venv do MIQA e instala deps (medmnist, torch, timm, etc.)
2. Loop por 16 tasks (15-30) — cada uma:
   - Envia prompt para Gemma4 via Ollama API (`http://localhost:11434`)
   - Recebe codigo Python
   - Aplica auto-patcher (remove IPython, corrige pandas.append)
   - Executa com timeout 600s
   - Retry ate 3 vezes se falhar
3. Gera `miqa_run_summary.csv` com status de cada task

## Tasks que Serao Rodadas

| ID | Descricao | Output |
|----|-----------|--------|
| 15 | ResNet18 em ChestMNIST (fix da API antiga) | chestmnist_resnet18.csv |
| 16 | Benchmark 3x3 (3 datasets x 3 redes) | benchmark_3x3.csv |
| 17 | Feature extraction ResNet18 | features_resnet18.npy |
| 18 | t-SNE + UMAP dos embeddings | embeddings_*.html |
| 19 | Data quality metrics (SNR, contrast) | image_quality.csv |
| 20 | Out-of-distribution detection | ood_auc.csv |
| 21 | Adversarial robustness (FGSM) | adv_fgsm.csv |
| 22 | Test-time augmentation | tta_gains.csv |
| 23 | MC Dropout uncertainty | uncertainty.csv |
| 24 | Transfer learning vs from-scratch | transfer_vs_scratch.csv |
| 25 | Label smoothing + Mixup | regularization.csv |
| 26 | Focal loss vs BCE | focal_vs_bce.csv |
| 27 | Knowledge distillation | distillation.csv |
| 28 | INT8 quantization | quantization.csv |
| 29 | Grad-CAM | gradcam_samples.png |
| 30 | Relatorio final HTML | miqa_final_report.html |

## Copiar Resultados de Volta

Quando terminar:
```bash
scp -P 2222 -r oftalmousp@dgx.retina.ia.br:~/jv-teste/miqa_backend/autoresearch/gemma4_experiments/ \
    /Users/jv/Documents/GitHub/MIQA_Backend_Local/autoresearch_dgx/results/
```

## Monitoramento

```bash
# Na DGX, em outro terminal:
tmux attach -t miqa_v2          # ver output
tail -f ~/jv-teste/miqa_backend/autoresearch/logs/task_*.log

# Status rapido:
ls ~/jv-teste/miqa_backend/autoresearch/gemma4_experiments/ | wc -l
```

## Troubleshooting

**"Ollama connection refused"**
```bash
systemctl --user start ollama  # ou: ollama serve &
```

**"Gemma4 model not found"**
```bash
ollama pull gemma4
```

**Task falha 3 tentativas**
- Ver log: `cat logs/task_XX.log`
- Se erro for de API medmnist, recriar script manualmente (sem Gemma4)
- Padrao de fix manual: criar `scripts_manual/task_XX.py`

---

*Gerado em 16 de abril de 2026*
