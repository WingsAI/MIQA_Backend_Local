# MIQA Backend API — Railway Deploy Guide

## Arquitetura (Opção C)

```
┌─────────────────────────────────────────┐
│  FRONTEND (Vue/React)                   │
│  fadex_medicina_projeto1                │
│  miqafront-production.up.railway.app    │
└──────────────┬──────────────────────────┘
               │ POST /analyze
               │ multipart/form-data
               ▼
┌─────────────────────────────────────────┐
│  BACKEND API (Python/FastAPI)           │
│  MIQA_Backend_Local                     │
│  miqa-api.up.railway.app (novo)         │
│                                         │
│  • CPU-only Random Forest               │
│  • 4 modelos pré-carregados             │
│  • Inferência < 50ms                    │
└─────────────────────────────────────────┘
```

## Deploy no Railway

### 1. Criar novo serviço no Railway

```bash
# No Railway CLI (ou dashboard web)
railway login
railway init --name miqa-api
```

### 2. Configurar Variáveis de Ambiente

No Railway Dashboard → Variables:

```
PORT=8000
PYTHONUNBUFFERED=1
```

### 3. Upload dos Modelos (CRITICAL)

Os modelos `.pkl` NÃO estão no GitHub. Você precisa fazer upload:

**Opção A: Railway Volume (Recomendado)**
1. Railway Dashboard → seu serviço → Volumes
2. Create Volume → mount path: `/app/miqa/ml_models/checkpoints`
3. Use Railway CLI para fazer upload:
   ```bash
   railway volume upload miqa-api /path/to/checkpoints miqa/ml_models/checkpoints
   ```

**Opção B: Upload manual via Dashboard**
1. Vá para "Deployments" → "Settings"
2. Em "Start Command", adicione um script que baixa os modelos:
   ```bash
   wget -O models.zip SEU_LINK.zip && unzip models.zip && uvicorn miqa.api:app --host 0.0.0.0 --port $PORT
   ```

**Opção C: Commitar os .pkl (não recomendado)**
```bash
# Se quiser commitar (arquivos são ~5-20MB cada)
git add miqa/ml_models/checkpoints/*/*.pkl
# Mas isso aumenta o repo significativamente
```

### 4. Conectar o Frontend ao Backend

No código do frontend (`fadex_medicina_projeto1`), mude a URL da API:

```javascript
// Antes (se estava mockado ou local)
const API_URL = 'http://localhost:8000'

// Depois (Railway)
const API_URL = 'https://miqa-api.up.railway.app'
// ou o domínio que o Railway gerar
```

### 5. Testar

```bash
# Health check
curl https://miqa-api.up.railway.app/health

# Analisar imagem
curl -X POST \
  -F "file=@sua_imagem.png" \
  -F "modality=rx" \
  -F "body_part=chest" \
  https://miqa-api.up.railway.app/analyze
```

## Endpoints da API

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/` | GET | Info do serviço |
| `/health` | GET | Health check + modelos carregados |
| `/models` | GET | Lista modelos disponíveis |
| `/analyze` | POST | Analisa imagem (multipart/form-data) |
| `/metrics` | GET | Métricas do sistema |

## Estrutura do Request/Response

### POST /analyze

**Request:**
```bash
curl -X POST \
  -F "file=@imagem.png" \
  -F "modality=rx" \
  -F "body_part=chest" \
  https://miqa-api.up.railway.app/analyze
```

**Response:**
```json
{
  "status": "success",
  "modality": "rx",
  "body_part": "chest",
  "score": 78.5,
  "confidence": 0.85,
  "features": {},
  "processing_time_ms": 45.2
}
```

## Troubleshooting

### "No models found"
Os checkpoints `.pkl` não foram carregados. Verifique:
1. O Volume está montado em `/app/miqa/ml_models/checkpoints`?
2. Os arquivos `.pkl` estão no diretório correto?

### "CORS error" no frontend
Verifique se o domínio do frontend está na lista `allow_origins` em `miqa/api.py`.

### Timeout na primeira requisição
O modelo é carregado no startup, mas se o Railway "dorme" o serviço, a primeira requisição pode demorar. Configure "Always On" no Railway (pago) ou use um healthcheck cron.

## Preços Railway

- **Starter (Gratuito):** $5 crédito/mês, serviço "dorme" após inatividade
- **Developer ($5/mês):** Serviço sempre ligado, 1GB RAM
- **Pro ($20/mês):** 2GB RAM, múltiplos serviços

Para produção médica, recomendo **Developer** para evitar cold start.