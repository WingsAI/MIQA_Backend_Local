# Plano de Migração A: Backend Serve Frontend

## Visão

FastAPI serve o frontend buildado como arquivos estáticos. Um único container, uma única URL, zero CORS.

---

## Arquitetura

```
┌─────────────────────────────────────────┐
│           Railway (1 serviço)           │
│                                         │
│  ┌──────────────┐    ┌──────────────┐  │
│  │   FastAPI    │────│    ML/RFF    │  │
│  │   /analyze   │    │   Models     │  │
│  │   /health    │    └──────────────┘  │
│  │   /models    │                      │
│  └──────┬───────┘                      │
│         │                               │
│  ┌──────┴───────┐                      │
│  │   Static     │  /, /miqa, /assets   │
│  │   Files      │  (Next.js buildado)  │
│  └──────────────┘                      │
│                                         │
│  Porta: 8000                            │
│  URL: https://miqa.up.railway.app       │
└─────────────────────────────────────────┘
```

**Rotas:**
- `GET /` → Dashboard MIQA (HTML)
- `POST /analyze` → API de análise
- `GET /health` → Health check
- `GET /models` → Lista modelos

---

## Estrutura de Diretórios Final

```
miqa-unified/
├── backend/
│   ├── miqa/
│   │   ├── __init__.py
│   │   ├── api.py              # FastAPI + static files
│   │   ├── ml_models/
│   │   │   ├── __init__.py
│   │   │   ├── predict.py
│   │   │   ├── train_v2.py
│   │   │   └── checkpoints/    # .pkl models
│   │   ├── anatomy/
│   │   │   ├── __init__.py
│   │   │   ├── detector.py
│   │   │   └── metrics.py
│   │   └── pipelines/
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx        # Dashboard principal
│   │   │   ├── layout.tsx
│   │   │   └── globals.css
│   │   ├── components/
│   │   │   ├── MIQAAnalysis.tsx
│   │   │   ├── Header.tsx
│   │   │   └── Sidebar.tsx
│   │   └── services/
│   │       └── api.ts          # API client (paths relativos)
│   ├── public/
│   ├── package.json
│   ├── next.config.js          # output: 'export'
│   └── Dockerfile
│
├── docker-compose.yml          # Dev local
├── Dockerfile                  # Produção multi-stage
├── railway.json                # Config deploy
├── .dockerignore
├── .gitignore
└── README.md
```

---

## Passo a Passo Detalhado

### Etapa 1: Criar Estrutura (30 min)

```bash
# Criar diretório
mkdir miqa-unified
cd miqa-unified
git init

# Copiar backend
cp -r ../MIQA_Backend_Local/* backend/

# Copiar frontend (apenas webapp/)
cp -r ../fadex_medicina_projeto1/webapp/* frontend/

# Criar diretórios
mkdir -p backend/static frontend/dist
```

### Etapa 2: Configurar Frontend para Export Estático (15 min)

```javascript
// frontend/next.config.js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  distDir: 'dist',
  images: {
    unoptimized: true,  // Necessário para static export
  },
  // API calls usam paths relativos
  env: {
    NEXT_PUBLIC_API_URL: '',  // Vazio = mesma origem
  }
}

module.exports = nextConfig
```

```typescript
// frontend/src/services/api.ts
// Alterar de:
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
// Para:
const API_BASE_URL = '';  // Mesma origem

// Ou simplesmente usar paths relativos:
fetch('/analyze', {...})
fetch('/health', {...})
```

### Etapa 3: Configurar FastAPI para Servir Frontend (20 min)

```python
# backend/miqa/api.py

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import os

app = FastAPI(
    title="MIQA",
    description="Medical Image Quality Assessment",
    version="1.1.0",
)

# API Routes
@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    # ... lógica de análise ...
    pass

@app.get("/models")
async def models():
    # ... lista modelos ...
    pass

# Servir frontend estático (só em produção)
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists() and any(static_dir.iterdir()):
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
else:
    @app.get("/")
    async def root():
        return {"message": "MIQA API - Frontend não buildado"}
```

### Etapa 4: Dockerfile Multi-Stage (30 min)

```dockerfile
# ==========================================
# Stage 1: Build Frontend
# ==========================================
FROM node:18-alpine AS frontend-builder

WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --only=production

COPY frontend/ ./
RUN npm run build
# Gera: /build/dist (HTML, CSS, JS estáticos)

# ==========================================
# Stage 2: Python Backend
# ==========================================
FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copiar dependências Python
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código backend
COPY backend/miqa ./miqa

# Copiar frontend buildado
COPY --from=frontend-builder /build/dist ./static

# Variáveis de ambiente
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "miqa.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Etapa 5: Docker Compose para Dev (10 min)

```yaml
# docker-compose.yml
version: '3.8'

services:
  miqa:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./backend/miqa:/app/miqa
      - ./checkpoints:/app/checkpoints
    environment:
      - PORT=8000
    
  # Opcional: buildar frontend separado em dev
  frontend-dev:
    build: ./frontend
    ports:
      - "3000:3000"
    volumes:
      - ./frontend:/app
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
    profiles:
      - dev
```

### Etapa 6: Railway Config (15 min)

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile"
  },
  "deploy": {
    "startCommand": "python -m uvicorn miqa.api:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 30,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

---

## Checklist de Migração

### Pre-Migração
- [ ] Fazer backup dos 2 repositórios
- [ ] Verificar se modelos .pkl estão em um lugar acessível
- [ ] Confirmar que `npm run build` funciona no frontend

### Migração
- [ ] Criar estrutura de diretórios
- [ ] Copiar código backend
- [ ] Copiar e ajustar frontend
- [ ] Configurar `next.config.js` para export
- [ ] Ajustar API URLs para paths relativos
- [ ] Modificar `api.py` para servir static files
- [ ] Criar Dockerfile multi-stage
- [ ] Testar build local: `docker build -t miqa .`
- [ ] Testar execução: `docker run -p 8000:8000 miqa`
- [ ] Verificar se `/` serve o frontend
- [ ] Verificar se `/analyze` funciona

### Post-Migração
- [ ] Atualizar README.md
- [ ] Configurar Railway (novo projeto)
 [ ] Adicionar volume para modelos .pkl
- [ ] Fazer deploy
- [ ] Testar em produção
- [ ] Apagar repositórios antigos (opcional)

---

## Comandos Úteis

```bash
# Build completo
docker build -t miqa-unified .

# Rodar local
docker run -p 8000:8000 -v $(pwd)/checkpoints:/app/checkpoints miqa-unified

# Ver logs
docker logs -f miqa-unified

# Dev mode (backend + frontend separados)
docker-compose --profile dev up

# Build manual do frontend
cd frontend && npm run build
# Copiar dist para backend/static
cp -r frontend/dist/* backend/static/
```

---

## Vantagens desta Abordagem

1. **Um único deploy** no Railway
2. **Zero CORS** — tudo na mesma origem
3. **Zero configuração** de URLs
4. **Frontend pré-renderizado** — carrega rápido
5. **API sempre disponível** — mesma URL
6. **Simplifica CI/CD** — um único pipeline
7. **Menor custo** — um serviço no Railway

---

## Riscos e Mitigações

| Risco | Mitigação |
|-------|-----------|
| Frontend não builda | Testar `npm run build` antes |
| Static files não carregam | Verificar path no Dockerfile |
| Modelos .pkl são grandes | Usar Railway Volume ou LFS |
| Cache do browser | Adicionar hash nos assets |

---

## Próximos Passos

Se aprovar, começo a migração:
1. Criar estrutura
2. Copiar e ajustar código
3. Configurar build
4. Testar localmente
5. Preparar deploy

**Quer que eu execute agora?**
