# 📋 MIQA Backend — Resumo para Deploy (Outro Computador)

**Data:** 2026-04-30
**Repo:** https://github.com/WingsAI/MIQA_Backend_Local
**Branch:** main
**Último commit:** `007f70e` — feat(api): FastAPI REST API para deploy no Railway

---

## 🎯 O que está pronto

### 1. Arquitetura ML Lightweight (CPU-Only)

**REGRA:** Nenhuma rede neural. Apenas modelos leves em CPU.

- **Random Forest** (padrão) — 100 estimadores, max_depth=10
- **XGBoost** (opcional)
- **Ridge Regression** (fallback)
- Inferência: **< 50ms por imagem em CPU**

### 2. Modelos Treinados (4 datasets)

| Contexto | Dataset | Imagens | Val MAE | Val R² | Arquivo .pkl |
|----------|---------|---------|---------|--------|--------------|
| **RX / Tórax** | COVID-19 Radiography | 21k | 6.12 | 0.861 | `miqa/ml_models/checkpoints/rx/chest/rf_quality_model.pkl` |
| **US / Mama** | BUSI | 780 | 0.20 | 0.999 | `miqa/ml_models/checkpoints/us/breast/rf_quality_model.pkl` |
| **CT / Tórax** | COVID CT | 2k | 0.61 | 0.962 | `miqa/ml_models/checkpoints/ct/chest/rf_quality_model.pkl` |
| **MRI / Cérebro** | Brain Tumor | 3k | 1.77 | 0.843 | `miqa/ml_models/checkpoints/mri/brain/rf_quality_model.pkl` |

**Metadados JSON** (commitados no GitHub):
- `miqa/ml_models/checkpoints/*/rf_metadata.json`

### 3. Datasets Extraídos (NÃO estão no repo)

Local: `~/MIQA_datasets/`

```
~/MIQA_datasets/
├── rx/chest/covid_chest/          # COVID-19 Radiography (21k)
├── us/breast/busi/                # Breast Ultrasound (780)
├── ct/chest/covid_ct/             # COVID CT Scans (2k)
└── mri/brain/brain_tumor/         # Brain Tumor MRI (3k)
```

### 4. API FastAPI (Pronta para Deploy)

Arquivo: `miqa/api.py`

**Endpoints:**
```
POST /analyze  → Upload imagem, retorna score [0-100]
GET  /health   → Status + modelos carregados
GET  /models   → Lista modelos disponíveis
GET  /metrics  → Métricas do sistema
```

**Arquivos de deploy:**
- `Dockerfile` — Container Python 3.11
- `railway.json` — Configuração do Railway
- `deploy-railway.sh` — Script automatizado
- `RAILWAY_DEPLOY.md` — Guia completo

---

## 🚂 Como fazer o Deploy no Railway (Passo a Passo)

### Passo 1: Login Railway CLI

```bash
# Em outro computador, instalar Railway CLI:
npm install -g @railway/cli

# Login na conta WingsGroup (joao.victor@wingsgroup.ai)
railway login
```

**⚠️ IMPORTANTE:** A conta precisa ter um plano ativo (Developer $5/mês ou Pro $20/mês). O trial gratuito expirou.

### Passo 2: Clonar e entrar no repo

```bash
git clone https://github.com/WingsAI/MIQA_Backend_Local.git
cd MIQA_Backend_Local
```

### Passo 3: Criar projeto no Railway

```bash
railway init --name "miqa-api-backend"
```

### Passo 4: Fazer Deploy

```bash
# Opção A: Script automatizado
./deploy-railway.sh

# Opção B: Manual
railway link
railway up
```

### Passo 5: Upload dos Modelos (CRITICAL)

Os arquivos `.pkl` **NÃO estão no GitHub** (são grandes, ~5-20MB cada).

**Opção A: Railway Volume (Recomendado)**
1. Railway Dashboard → Seu serviço → Volumes
2. Create Volume → Mount path: `/app/miqa/ml_models/checkpoints`
3. Upload dos 4 arquivos:
   - `miqa/ml_models/checkpoints/rx/chest/rf_quality_model.pkl`
   - `miqa/ml_models/checkpoints/us/breast/rf_quality_model.pkl`
   - `miqa/ml_models/checkpoints/ct/chest/rf_quality_model.pkl`
   - `miqa/ml_models/checkpoints/mri/brain/rf_quality_model.pkl`

**Opção B: Commitar os .pkl (mais simples, mas aumenta o repo)**
```bash
git add miqa/ml_models/checkpoints/*/*.pkl
git commit -m "add: model checkpoints for deploy"
git push
railway up
```

### Passo 6: Conectar Frontend

No código do frontend (`fadex_medicina_projeto1`), mudar a URL da API:

```javascript
const API_URL = 'https://miqa-api-backend.up.railway.app';
// ou a URL que o Railway gerar
```

---

## 📊 Documentos Gerados

| Arquivo | Local | Descrição |
|---------|-------|-----------|
| Relatório Técnico | `apresentacao_executivo/miqa-relatorio-tecnico.html` | HTML completo com 5 partes |
| Dashboard Experimentos | `apresentacao_executivo/miqa-experiments.html` | Cards dos 4 modelos treinados |
| Guia Deploy | `RAILWAY_DEPLOY.md` | Instruções detalhadas de deploy |

---

## 🔬 Status dos Experimentos

### ✅ Feito
- [x] 21 métricas anatomy-aware implementadas
- [x] 14 testes sintéticos passando (100%)
- [x] 4 modelos ML treinados (RX/US/CT/MRI)
- [x] Data augmentation com degradações controladas
- [x] API FastAPI pronta
- [x] Docker e Railway config

### 🔄 Próximos Passos (Experimentos)
1. **Análise exploratória** dos datasets — ainda não fizemos análise completa das distribuições
2. **Treinar mais contextos** — RX crânio/extremidade, CT abdome, MRI joelho
3. **Validação cruzada** — testar modelos em imagens reais (não só sintético)
4. **Threshold clínico** — calibrar score 0-100 com radiologistas
5. **Pipeline completo** — integrar frontend → API → resultado

---

## 📁 Novos Arquivos no Repo

```
MIQA_Backend_Local/
├── miqa/
│   ├── anatomy/                  # Detector + métricas por anatomia
│   │   ├── detector.py
│   │   ├── metrics_rx.py
│   │   ├── metrics_us.py
│   │   ├── metrics_ct.py
│   │   └── metrics_mri.py
│   ├── ml_models/                # Modelos ML lightweight
│   │   ├── __init__.py
│   │   ├── train_lightweight.py  # Treinamento
│   │   ├── api.py                # FastAPI
│   │   ├── checkpoints/          # Modelos treinados (JSON only no git)
│   │   └── utils/
│   └── tests/
│       └── test_anatomy_metrics_synth.py
├── Dockerfile                    # Container para Railway
├── railway.json                  # Config Railway
├── deploy-railway.sh            # Script deploy
├── RAILWAY_DEPLOY.md            # Guia deploy
└── apresentacao_executivo/
    ├── miqa-relatorio-tecnico.html  # Atualizado com Parte 5
    └── miqa-experiments.html        # Dashboard com 4 modelos
```

---

## 🆘 Troubleshooting

### "No models found" na API
Os `.pkl` não foram carregados. Verifique se:
1. Os arquivos estão no Railway Volume
2. O mount path está correto: `/app/miqa/ml_models/checkpoints`

### "CORS error" no frontend
Adicione o domínio do frontend em `miqa/api.py`:
```python
allow_origins=["https://miqafront-production.up.railway.app"]
```

### Railway "Trial expired"
Fazer upgrade para Developer ($5/mês) no dashboard.

---

## 📞 Links Importantes

- **GitHub:** https://github.com/WingsAI/MIQA_Backend_Local
- **Frontend:** https://miqafront-production.up.railway.app
- **Railway Dashboard:** https://railway.app/dashboard
- **Relatório Técnico:** `apresentacao_executivo/miqa-relatorio-tecnico.html` (abrir no browser)

---

**Próximo passo:** Diga "pronto" quando terminar o deploy, ou vamos continuar com mais experimentos/análises dos datasets.