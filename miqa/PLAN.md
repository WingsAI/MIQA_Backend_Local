# MIQA — Plano: Autoresearch de novas métricas + Degradação controlada

Documento único, vivo, no repositório. Substitui qualquer "plan/notes" externo.
Atualizar in-place; não criar variantes.

---

## 0. Estado atual (referência)

Pipelines validados sintética e em dados reais:

| Modalidade | Métricas próprias                              | Dataset (Kaggle)                       | n   | Sintético |
|------------|------------------------------------------------|----------------------------------------|-----|-----------|
| RX         | SNR, CNR, exposure, edge_sharpness             | Kermany pneumonia (paultimothymooney)  | 328 | 5/5       |
| US         | speckle_snr, shadowing, depth_of_penetration, gain | BUSI (sabahesaraki)                | 100 | 4/4       |
| CT         | air_noise, hu_calibration, ring, streak        | Stroke DICOM (orvile)                  | TBD | 4/4       |
| MRI        | (futuro)                                       | fastMRI / IXI                          | —   | —         |

Universais (todas as modalidades): laplacian_var, tenengrad, entropy, rms_contrast,
clipping_pct, dynamic_range — 6/6 sintético PASS.

---

## 1. Plano A — Autoresearch de novas métricas

### 1.1. Hipótese
As métricas atuais foram **escolhidas pelo conhecedor (eu/você)** e validadas em
sintético. Existem provavelmente métricas relevantes que não pensamos ainda
— extraídas de artigos de IQA radiológica, blocos de processamento clássicos
(NPS, MTF presampled, BRISQUE/NIQE residuais), ou heurísticas data-driven.

### 1.2. Loop (manual, com revisão humana — sem Ollama por escolha sua)
Iteramos juntos no chat. Cada iteração:

```
1. PROPOSTA  — eu trago 3-5 candidatas, com referência (paper/livro) e racional físico
2. SPEC      — pra cada candidata: input/output, comportamento esperado vs degradação
3. CÓDIGO    — eu escrevo a função em miqa/metrics/<modalidade>_v2.py
4. TESTE     — bateria sintética que ELA precisa passar (mesmo padrão atual)
5. APLICA    — rodo nos subsets já baixados (RX 328, US 100, CT N)
6. CRÍTICA   — você olha:
                 - faz sentido visual?
                 - correlaciona ou é redundante com as existentes?
                 - destaca casos que as atuais perdem?
7. ACEITA    — métrica entra no pipeline oficial; senão, descarta
```

### 1.3. Candidatas que já tenho mapeadas (priorizadas)

Universais:
- **NIQE** (no-reference IQA, gaussian-distortion-trained) — pyiqa já instalado
- **BRISQUE** (no-ref clássico) — pyiqa
- **Noise Level Estimator (PCA)** de Liu et al. 2013 — implementação pura numpy
- **MTF presampled** via slanted edge (ISO 12233) — mede resolução real

RX:
- **NPS (Noise Power Spectrum) radial** — caracteriza textura do ruído
- **Lung field detection + SNR só dentro do pulmão** (anátomico, não cego)
- **Border completeness** — penaliza imagens cortadas
- **Marker/letter blob detection** — flags letras de chumbo cobrindo anatomia

US:
- **Acoustic shadow score angular** (Hellier-style)
- **Lateral resolution proxy** via PSF estimada em pequenas reflexões pontuais
- **Speckle anisotropy** — speckle alongado horizontalmente indica ângulo errado

CT:
- **Slice-to-slice consistency** quando temos volume
- **Radial NPS no centro do scan** — flagra ruído elevado
- **Beam-hardening cup detection** — perfil radial não-monotônico

### 1.4. Comparação A/B
Resultados ficam em `miqa/results/metric_comparison.csv` (uma linha por imagem,
colunas: métricas v1 + métricas v2). Análise:
- correlação Pearson/Spearman entre v1 e v2 (redundância)
- desacordos: top-10 imagens onde score muda mais de v1 pra v2 (você revisa)

### 1.5. O que NÃO faz parte deste plano
- Treinar modelos (volta pra classificação — saímos disso de propósito).
- Geração de código por LLM (você decidiu fazer manual comigo).
- Métricas full-reference (precisariam de versão "limpa" de cada imagem — tema
  do plano B).

---

## 2. Plano B — Degradação controlada (estende o A)

### 2.1. Hipótese
Pra confiar nas métricas precisamos saber **como elas variam** sob degradação
conhecida. Isso é validação além do "sintético phantom" inicial — usa imagens
reais + degradação controlada.

### 2.2. Mecânica
Pra cada imagem original *I* nos subsets:

```
gera I_d_k = degradar(I, parâmetro=k) para k em [k_min, k_max]
calcula  m_v1(I_d_k), m_v2(I_d_k) para todas as métricas e todo k
```

Salva tudo num único `miqa/results/degradation_grid.csv`:
```
file, modality, degradation, k, metric_name, value
```

### 2.3. Tipos de degradação (todos físicos, modalidade-aware)

Universais (qualquer modalidade):
- **Gaussian noise** σ ∈ {0.01, 0.02, 0.05, 0.1, 0.15}
- **Gaussian blur** σ ∈ {0.5, 1, 2, 4} px
- **Contraste comprimido** factor ∈ {0.8, 0.5, 0.3, 0.1}
- **Down-up resample** (perda de resolução) scale ∈ {0.5, 0.25}
- **JPEG re-encode** quality ∈ {90, 60, 30, 10}
- **Bit depth quantization** bits ∈ {12, 8, 6, 4}

Específicas:
- **RX**: rotação (5°, 10°, 30°), corte de borda (10%, 30%), saturação forçada
- **US**: ganho aumentado (saturação simulada), sombra sintética (faixa vertical)
- **CT**: ring artifact sintético, streak sintético, miscalibração HU (+50, +100, +500)

Implementadas em `miqa/synthetic/degradations_v2.py` (estende o módulo atual).

### 2.4. Análises esperadas (uma por gráfico, no consolidado)

1. **Curvas dose-resposta**: m_metric(k) por imagem — deve ser monotônica nas
   degradações relevantes pra ela.
2. **Sensibilidade**: derivada |dm/dk| média — métricas com sensibilidade ~0
   são inúteis pra detectar aquela degradação.
3. **Saturação**: existe k acima do qual m não muda mais? (cap natural)
4. **Cross-talk**: aplicar blur fez SNR mudar muito? (ele não deveria — SNR
   mede ruído, não nitidez. Cross-talk alto = métrica confundida.)

### 2.5. Score-card final por métrica

| Métrica | Detecta o que diz | Sensibilidade | Cross-talk | Decisão |
|---------|-------------------|---------------|------------|---------|
| SNR     | ruído → CAI       | dm/dσ alto    | blur baixo | keep    |
| ...     | ...               | ...           | ...        | ...     |

### 2.6. Saída consolidada (UM arquivo)

`miqa/results/MIQA_REPORT.html` — auto-contido com:
- estatísticas por modalidade (já temos)
- curvas de degradação (plano B)
- comparação v1 vs v2 (plano A)
- score-card de métricas
- 16 thumbnails representativos (4 por modalidade)

Sem proliferação de relatórios. Existentes (`rx_report.html`, `us_report.html`,
`ct_report.html`) ficam como artefatos de iteração; o consolidado os substitui
no fim.

---

## 3. Sequência de execução proposta

Ordem para você aprovar:

| Fase | Plano | O que entrega | Tempo Mac |
|------|-------|---------------|-----------|
| F1   | A     | NIQE+BRISQUE universais (pyiqa) + comparação v1 | 30 min |
| F2   | A     | NPS radial RX + lung-mask SNR                   | 1h     |
| F3   | A     | speckle_anisotropy US + lateral_resolution      | 1h     |
| F4   | A     | slice_consistency CT (precisa volume agrupado)  | 1h     |
| F5   | B     | módulo de degradação + grid universal           | 1h     |
| F6   | B     | rodar grid em RX/US/CT (~300 imgs × 6 degr × 4k)| 1-2h CPU |
| F7   | —     | consolidar `MIQA_REPORT.html` único             | 1h     |

**Total: ~6-8h de trabalho efetivo**, dividido em sessões.

Não faço nada disso até você aprovar a fase. Cada fase encerra com seu OK
explícito (ou pedido de ajuste) antes de seguir.
