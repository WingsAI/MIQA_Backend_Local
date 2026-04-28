# MIQA — Achados consolidados

Documento vivo. Atualizar quando uma observação muda. Não fazer cópia/fork.
Complementa `PLAN.md` (intenção) com o que **de fato observamos rodando**.

---

## 1. Escopo coberto

| Modalidade | Dataset                            | n   | Métricas v1                     | v2 universal | v2 modalidade |
|------------|-------------------------------------|-----|----------------------------------|--------------|---------------|
| RX         | Kermany pneumonia (Kaggle JPEG)    | 328 | SNR · CNR · exposure · sharpness | NIQE+BRISQUE | lung_snr · NPS |
| US         | BUSI breast (Kaggle PNG)           | 100 | speckle_snr · shadow · DoP · gain | NIQE+BRISQUE | speckle_anisotropy · lateral_res · TGC |
| CT         | Stroke head (Kaggle DICOM)         | 300 | air_noise · HU calib · ring · streak | NIQE+BRISQUE | slice_consistency (vol) |
| MRI        | Brain MRI (Kaggle DICOM)           | 85  | NEMA SNR · ghosting · bias · motion | NIQE+BRISQUE | — |

Total: **813 imagens reais processadas**, 16.430 linhas de degradação,
1 grid sintético por métrica (todos PASS).

---

## 2. Achados sobre métricas

### 2.1. Universais (`miqa/metrics/universal.py`)

- **`laplacian_var`** — saiu do scorecard como `drop_redundant` em todas as
  modalidades (uniqueness ~0.22). Confirmado: F5 mostrou Δ=25 832 em ruído
  vs <100 em outras degradações — é um sensor de ruído puro que escala com σ²
  do ruído. Substituído por:
- **`laplacian_snr`** (D) — mediana(|Lap|p95) / MAD(|Lap|), robusto a ruído
  multiplicativo. Cai com blur (estrutura), estável sob ruído puro.
- **`tenengrad`, `dynamic_range`, `clipping_pct`, `rms_contrast`** —
  redundantes entre si nas distribuições reais (ρ Spearman > 0.7).
- **`entropy`** — sobrevive ao scorecard em RX (uniq 0.72), interessante.

### 2.2. RX

- **`rx.snr`** ficou em `review` (F5: ρ baixo com degradações; pegava
  diferenças sutis mas não era monotônico). Refinado em F2 (mediana de 9
  ROIs com σ-floor) — sumiu a cauda absurda (max 50.980 → max 176).
- **`rx_v2.lung_snr`** — `keep`. Uniqueness 0.44, ρ=-0.56 com clipping
  (faz sentido clínico: clipping queima detalhe pulmonar). 9/328 falham
  na detecção da máscara — taxa aceitável.
- **`rx_v2.nps_high_frac`** — `review`. ρ=-0.35 com sharpness, ρ=0.27 com
  entropy. Captura nuance espectral mas não decisivo.
- **`rx.exposure`** — flag de overexposure em 4.3% Kermany (vs 12% no
  covid-dataset com fotos de papers). Threshold 0.7 razoável; não calibrado.

### 2.3. US

- **`us_v2.speckle_anisotropy`** — `keep`. Uniqueness **0.81** (quase
  totalmente nova). Mediana 3.69 em BUSI, esperado ~1 pra US bem ajustado.
- **`us_v2.lateral_resolution_px`** — `keep`. ROI=192 + sub-pixel FWHM. 50%
  satura em BUSI: speckle de mama é estruturalmente macro, não bug. Flag
  `saturated` em extras.
- **`us_v2.tgc_cov`** — `drop_redundant`. ρ=-0.87 com `us.depth_of_penetration`
  existente — manter um dos dois (DoP é mais clinicamente legível).
- **`us.shadowing`** — `keep` (uniq 0.72). Bom score independente.
- **`us.gain`** — todos 100% "ok" no BUSI: dataset clínico bem ajustado, não
  testou o flag em condições adversas.

### 2.4. CT

- **`ct.hu_calibration`** revelou heterogeneidade do dataset stroke:
  102/300 ok vs 198/300 miscalibrated. Não é falha da métrica — é a verdade:
  ~66% dos DICOMs têm `RescaleIntercept` inconsistente.
- **`ct.air_noise` mediana 0** em CT cranial — assumiu cantos = ar, mas
  cabeça tem crânio nos cantos. Limitação modalidade-específica (funcionaria
  em CT abdominal/torácico). Anotada em comentário no código.
- **CT métricas v1 NÃO estão no F5 grid** porque exigem HU e o grid roda
  degradações em [0,1]. Por isso scorecard CT está sparse — só universais.
- **`ct_v2.slice_consistency`**: anomaly_pct mediana 15% reflete que
  filenames numéricos misturam pacientes (metadados anonimizados → não
  há SeriesInstanceUID pra agrupar). Pseudo-volumes de 20 slices conscutivos
  nem sempre são do mesmo paciente.

### 2.5. MRI

- **`mri.nema_snr`** retornou NaN em 31/85 imagens — cantos com tecido (não
  ar) em cortes apertados/croppped. Aceitável ~36% taxa de falha em dataset
  de papers.
- **`mri.ghosting`** funciona após dois bugs corrigidos durante F6:
  1. Mascara conectava tecido + fantasma via `MORPH_CLOSE` (removido)
  2. Phantom de teste tinha tecido grande demais (rad=h/3 → rad=h/5)
- **`mri.bias_field`**, **`mri.motion_hf`** — sintético OK, distribuição
  real mediana 0.30 e 0.003 respectivamente.

### 2.6. v2 universal (NIQE/BRISQUE)

- **NIQE** medianas: RX 4.57 · US 6.01 · CT 6.73 · MRI 6.82.
  Treinado em fotografia natural — RX se aproxima mais (b&w "natural"),
  US/CT/MRI ficam altos mas **consistentes dentro da modalidade**: usável
  como ranking interno, NÃO como score absoluto cross-modality.
- **BRISQUE** é a métrica mais "universal" no F5: responde forte a TODAS
  as degradações (Δ 50-130 uniforme em RX), não tem viés específico.
  Boa âncora pra v1+v2 comparison.
- Não existe NaN em nenhuma das 813 imagens — robusto.

---

## 3. Achados estruturais

### 3.1. Limites do método "phantom + degradação"

- **Phantom só captura física que pensamos modelar.** O bug de ghosting
  só apareceu porque construímos o phantom certo. Métrica que parecia
  funcionar 3 testes seguidos quebrou no 4° (lateral_res saturando).
  Custo: cada métrica precisa pelo menos 2 phantoms (caso bom e caso ruim).
- **Degradações em [0,1] não cobrem o domínio inteiro.** CT métricas em
  HU ficaram fora do scorecard. Solução possível: aplicar degradações na
  HU diretamente (escalando σ pelo range típico de tecido).
- **Real ≠ phantom.** `lung_snr` passou no sintético (rad=h/4 phantom) mas
  falha em 9/328 RX reais. Phantom não tinha rotação, marcador, cropping.

### 3.2. Limites dos datasets usados

- **RX Kermany**: pediátrico, JPEG, sem DICOM tags. Funciona pra teste de
  pipeline mas não pra exposure index real.
- **BUSI US**: dataset *limpo* — todas 100% "gain ok", pouco shadowing.
  Pra estressar shadowing precisamos de ultrasom ginecológico ou cardio.
- **Stroke CT**: heterogêneo no header (RescaleIntercept inconsistente),
  metadados de série anonimizados. Pseudo-volumes não preservam paciente.
- **Brain MRI**: alguns reformatados/cropped (sem cantos limpos de ar) →
  31/85 NEMA falha.

Estes não são bugs do método — são realidade clínica que o método precisa
detectar.

### 3.3. Score unificado cross-modality (B)

- 13 métricas keep entram (RX 6, US 5, CT 2, MRI 0 ainda — falta rodar
  scorecard com MRI no grid). Atualizado com MRI no grid → 14 keep total.
- Distribuição mediana ~50 em todas as modalidades (esperado: percentil
  interno). Std 11-14 RX/US/CT, 29 MRI (n=85, mais ruidoso).
- **Limitação**: ranking-based. Imagem boa numa modalidade ruim pode ter
  score 90 sem ser absolutamente boa. É comparação intra, agregada.

---

## 4. Decisões de design (post hoc)

- **Sem treinar classificador.** Saímos disso de propósito (commit
  `110ffc9` foi onde eu/agente errei o escopo; recomeçamos em `4a07a54`).
- **Sem LLM gerador (Karpathy autoresearch via Ollama).** Decisão do
  usuário: iterar manualmente comigo na conversa, com cada métrica passando
  por phantom sintético antes de aceitar.
- **Um único HTML consolidado (`apresentacao_executivo/miqa-experiments.html`).**
  Atualiza in-place a cada experimento, deployado pelo Vercel.
- **Datasets via Kaggle CLI**. Pequenos, reproduzíveis,
  `.gitignore` exclui o conteúdo binário.
- **Phantom = critério de aceitação.** Métrica nova só vira "oficial" se
  passa em N degradações sintéticas com comportamento esperado documentado.

---

## 5. O que falta (próximos)

- **CT em HU no grid de degradação** — refatorar `run_degradation_grid` pra
  aplicar degradações em HU (escalando σ). Vai habilitar scorecard CT
  completo (atualmente só universais).
- **Escala de subsets** (E adiada): RX Kermany inteiro (~5800), CT volumes
  preservando estrutura de pasta para `slice_consistency` real.
- **`us.gain` flag não testada em US ruim.** Buscar dataset US adverso
  (ex: ultrassom obstétrico de baixa qualidade) pra ver flag disparar.
- **Refinar `lung_snr` quando máscara falha** (9/328 atualmente NaN). Talvez
  fallback pra ROI homogênea genérica.
- **Refinar score unificado**: hoje é puramente ranking. Adicionar
  componente absoluto baseado em valor da métrica vs threshold clínico.
