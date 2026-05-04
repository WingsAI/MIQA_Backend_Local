# Plano de Unificação: Projeto MIQA Único

## Visão Geral

Unificar `MIQA_Backend_Local` (backend Python/FastAPI) e `fadex_medicina_projeto1` (frontend Next.js) em um **monorepo único** com deploy integrado.

---

## Estrutura Proposta

```
miqa/
├── backend/              # FastAPI + ML (atual MIQA_Backend_Local)
│   ├── miqa/
│   │   ├── api.py
│   │   ├── ml_models/
│   │   ├── anatomy/
│   │   └── pipelines/
│   ├── checkpoints/      # Modelos .pkl (git-lfs ou .gitignore)
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/             # Next.js (atual fadex_medicina_projeto1/webapp)
│   ├── src/
│   ├── package.json
│   ├── next.config.js
│   └── Dockerfile
│
├── shared/               # Tipos, schemas, constantes
│   ├── types/
│   └── schemas/
│
├── docs/                 # Documentação unificada
├── scripts/              # Scripts de deploy, setup, etc.
├── docker-compose.yml    # Desenvolvimento local
├── Dockerfile            # Produção (multi-stage)
├── railway.json          # Config Railway
└── README.md
```

---

## Opções de Arquitetura

### Opção A: Backend Serve Frontend (Recomendada)

**Como funciona:**
1. Frontend builda para arquivos estáticos (`next export` ou `output: 'export'`)
2. FastAPI serve os arquivos estáticos em `/`
3. API fica em `/api/*` ou `/analyze`, `/health`
4. **Um único container**, um único domínio

**Vantagens:**
- Deploy ultra-simples (um serviço Railway)
- Sem problemas de CORS
- Sem configuração de múltiplas URLs
- Frontend é pré-renderizado, carrega rápido

**Desvantagens:**
- Frontend não tem SSR (Server-Side Rendering)
- Menos flexível para SEO complexo (não é problema aqui)

**Implementação:**
```python
# backend/miqa/api.py
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# API endpoints
app.post("/analyze")
app.get("/health")

# Frontend estático
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")
```

### Opção B: Proxy Reverso (Nginx)

**Como funciona:**
- Nginx roteia `/` → frontend, `/api/` → backend
- Dois containers, um proxy

**Vantagens:**
- SSR funciona normalmente
- Separação limpa

**Desvantagens:**
- Mais complexo
- Dois serviços Railway (ou um com docker-compose)

### Opção C: Embed React no Backend

**Como funciona:**
- Substituir Next.js por React puro (Vite)
- Build como assets estáticos
- Template HTML simples servido pelo FastAPI

**Vantagens:**
- Zero configuração
- Build super rápido
- Menor bundle size

**Desvantagens:**
- Perde benefícios do Next.js (mas para dashboard interno, OK)

---

## Plano de Migração (Passo a Passo)

### Fase 1: Preparação (2-3h)
1. **Criar estrutura monorepo**
   ```bash
   mkdir miqa-unified
   cd miqa-unified
   git init
   ```

2. **Mover backend**
   ```bash
   cp -r ../MIQA_Backend_Local/* backend/
   # Ajustar paths em imports
   ```

3. **Mover frontend**
   ```bash
   cp -r ../fadex_medicina_projeto1/webapp/* frontend/
   ```

4. **Criar shared types**
   - Copiar interfaces TypeScript para `shared/types/`
   - Criar schemas Pydantic compartilhados

### Fase 2: Integração Frontend-Backend (3-4h)
1. **Configurar Next.js para export estático**
   ```js
   // frontend/next.config.js
   module.exports = {
     output: 'export',
     distDir: '../backend/frontend_dist',
   }
   ```

2. **Ajustar API URL no frontend**
   - Remover `NEXT_PUBLIC_API_URL`
   - Usar paths relativos: `/analyze`, `/health`

3. **Configurar FastAPI para servir frontend**
   ```python
   # Adicionar ao api.py
   from fastapi.staticfiles import StaticFiles
   
   # Só monta se o diretório existir
   if Path("frontend_dist").exists():
       app.mount("/", StaticFiles(directory="frontend_dist", html=True), name="frontend")
   ```

4. **Criar fallback para desenvolvimento**
   - Se frontend_dist não existir, API funciona normalmente
   - Frontend pode rodar standalone com `npm run dev`

### Fase 3: Docker Unificado (2h)
1. **Multi-stage Dockerfile**
   ```dockerfile
   # Stage 1: Build frontend
   FROM node:18-alpine AS frontend-build
   WORKDIR /app/frontend
   COPY frontend/package*.json ./
   RUN npm ci
   COPY frontend/ ./
   RUN npm run build
   
   # Stage 2: Python backend
   FROM python:3.11-slim
   WORKDIR /app
   
   # Instalar dependências Python
   COPY backend/requirements.txt ./
   RUN pip install -r requirements.txt
   
   # Copiar backend
   COPY backend/ ./
   
   # Copiar frontend buildado
   COPY --from=frontend-build /app/frontend/dist ./frontend_dist
   
   # Expor porta
   EXPOSE 8000
   
   CMD ["python", "-m", "miqa.api"]
   ```

2. **docker-compose.yml para dev**
   ```yaml
   version: '3.8'
   services:
     backend:
       build: ./backend
       ports:
         - "8000:8000"
       volumes:
         - ./backend:/app
         - ./checkpoints:/app/checkpoints
     
     frontend:
       build: ./frontend
       ports:
         - "3000:3000"
       volumes:
         - ./frontend:/app
       environment:
         - NEXT_PUBLIC_API_URL=http://localhost:8000
   ```

### Fase 4: Deploy Railway Simplificado (1h)
1. **Um único serviço** no Railway
2. ** railway.json ** atualizado
3. **Variáveis de ambiente** mínimas
4. **Volume** para modelos .pkl

### Fase 5: Documentação e Testes (2h)
1. README unificado
2. Scripts de setup (`setup.sh`, `start.sh`)
3. Testes integrados

---

## Vantagens da Unificação

| Antes (2 projetos) | Depois (1 projeto) |
|-------------------|-------------------|
| 2 repositórios | 1 monorepo |
| 2 deploys Railway | 1 serviço |
| Configurar CORS | Zero CORS |
| 2 URLs (frontend + API) | 1 URL única |
| Sincronizar versions | Version única |
| Context switching | Fluxo integrado |

---

## Timeline Estimada

- **Dia 1:** Fases 1-2 (estrutura + integração)
- **Dia 2:** Fase 3 (Docker) + testes locais
- **Dia 3:** Fase 4 (deploy Railway) + ajustes
- **Dia 4:** Fase 5 (docs) + validação

**Total: 3-4 dias de trabalho**

---

## Decisões a Tomar

1. **Qual opção de arquitetura?** (A - Backend serve frontend)
2. **Manter Next.js ou simplificar para React puro?**
3. **Onde hospedar modelos .pkl?** (Railway Volume / S3 / treinar no deploy)
4. **Manter histórico Git dos 2 projetos?** (opcional)

---

## Próximos Passos Imediatos

Se aprovar o plano, posso começar:
1. Criar estrutura monorepo
2. Migrar código
3. Configurar integração
4. Testar localmente

**O que acha do plano? Quer começar?**
