# 🔄 ARQUITETURA E FLUXO - Backend Local MIQA

## 🎯 Visão Geral

O sistema funciona como uma **máquina de estados** onde cada componente tem uma responsabilidade específica e todos se comunicam através do **SQLite** (banco de dados central).

---

## 📊 Arquitetura Completa

```
┌─────────────────────────────────────────────────────────────────┐
│                        PASTA WATCH                               │
│                    (Imagens chegam aqui)                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    1. FILE LISTENER                              │
│  - Monitora pasta watch/                                         │
│  - Detecta novos arquivos                                        │
│  - Verifica se arquivo está estável                             │
│  - Gera UID (hash SHA256)                                        │
│  - Registra no SQLite                                            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SQLITE DATABASE                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ queue_items (FILA CENTRAL)                               │   │
│  │ - item_uid (PK)                                          │   │
│  │ - path (caminho da imagem)                               │   │
│  │ - cloud_status (PENDING/UPLOADING/UPLOADED/FAILED)      │   │
│  │ - local_status (PENDING/PROCESSING/DONE/FAILED)         │   │
│  │ - locked_until (controle de concorrência)                │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ system_state                                             │   │
│  │ - connectivity_state (ONLINE/OFFLINE/DEGRADED)           │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────┬────────────────────────────┬────────────────────────────┘
         │                            │
         │                            │
    ┌────▼────┐                  ┌────▼────┐
    │ ONLINE? │                  │OFFLINE? │
    └────┬────┘                  └────┬────┘
         │                            │
         ▼                            ▼
┌─────────────────────┐    ┌─────────────────────┐
│ 2. CONNECTIVITY MGR │    │ 3. LOCAL WORKER     │
│ - Faz healthcheck   │    │ - Pega itens com    │
│ - Mede latência     │    │   local_status=     │
│ - Atualiza estado   │    │   PENDING           │
│ - Histerese         │    │ - Processa com MIQA │
└─────────┬───────────┘    │ - Salva em results/ │
          │                │ - Marca DONE        │
          ▼                └─────────────────────┘
┌─────────────────────┐
│ 4. CLOUD WORKER     │
│ - Pega itens com    │
│   cloud_status=     │
│   PENDING           │
│ - Envia para API    │
│ - Marca UPLOADED    │
└─────────────────────┘
```

---

## 🔄 Fluxo Detalhado Passo a Passo

### **Cenário 1: Sistema ONLINE**

```
1. IMAGEM CHEGA
   watch/test_image.jpg
   
2. FILE LISTENER detecta
   ├─ Verifica estabilidade (5 checks)
   ├─ Gera UID: sha256(conteúdo)
   └─ INSERT INTO queue_items:
      - item_uid: "abc123..."
      - path: "watch/test_image.jpg"
      - cloud_status: "PENDING"
      - local_status: "PENDING"

3. CONNECTIVITY MANAGER verifica
   ├─ GET /health → 200 OK
   ├─ Latência: 100ms
   └─ UPDATE system_state:
      - connectivity_state: "ONLINE"

4. CLOUD WORKER processa
   ├─ SELECT * FROM queue_items 
   │  WHERE cloud_status='PENDING'
   ├─ UPDATE: cloud_status='UPLOADING'
   ├─ POST /api/v1/miqa/analyze
   │  - file: test_image.jpg
   │  - modality: mri
   ├─ Resposta: {"score": 85.5, ...}
   └─ UPDATE: cloud_status='UPLOADED'

5. LOCAL WORKER não processa
   └─ Verifica: connectivity_state='ONLINE'
      → Não faz nada (aguarda)

RESULTADO: Imagem processada na NUVEM ✅
```

---

### **Cenário 2: Sistema OFFLINE**

```
1. IMAGEM CHEGA
   watch/test_image.jpg
   
2. FILE LISTENER detecta
   └─ INSERT INTO queue_items:
      - cloud_status: "PENDING"
      - local_status: "PENDING"

3. CONNECTIVITY MANAGER verifica
   ├─ GET /health → TIMEOUT
   ├─ 3 falhas consecutivas
   └─ UPDATE system_state:
      - connectivity_state: "OFFLINE"

4. CLOUD WORKER não processa
   └─ Verifica: connectivity_state='OFFLINE'
      → Não faz nada (aguarda)

5. LOCAL WORKER processa
   ├─ SELECT * FROM queue_items 
   │  WHERE local_status='PENDING'
   ├─ UPDATE: local_status='PROCESSING'
   ├─ Carrega imagem
   ├─ Processa com MIQA
   ├─ Salva: results/abc123.json
   └─ UPDATE: 
      - local_status='DONE'
      - local_result_path='results/abc123.json'

RESULTADO: Imagem processada LOCALMENTE ✅
```

---

## 🗄️ SQLite como Fonte da Verdade

O SQLite é o **coração do sistema**. Todos os componentes leem e escrevem nele:

```
┌────────────────────────────────────────────────────────┐
│                    SQLITE DATABASE                      │
│                  (Fonte da Verdade)                     │
├────────────────────────────────────────────────────────┤
│                                                         │
│  QUEM ESCREVE:                                          │
│  ✍️  File Listener    → Novos itens                    │
│  ✍️  Connectivity Mgr → Estado de rede                 │
│  ✍️  Cloud Worker     → Status de upload               │
│  ✍️  Local Worker     → Status de processamento        │
│                                                         │
│  QUEM LÊ:                                               │
│  👁️  Cloud Worker     → Itens pendentes para cloud     │
│  👁️  Local Worker     → Itens pendentes para local     │
│  👁️  Connectivity Mgr → Estado atual                   │
│  👁️  CLI (status)     → Estatísticas                   │
│                                                         │
└────────────────────────────────────────────────────────┘
```

---

## 🔐 Controle de Concorrência

Para evitar que 2 workers processem o mesmo item:

```python
# Worker pega item
item = get_pending_cloud()  # item_uid: "abc123"

# Faz "claim" (lock)
UPDATE queue_items 
SET cloud_status = 'UPLOADING',
    locked_until = NOW() + 5 minutes
WHERE item_uid = 'abc123'

# Processa...

# Se outro worker tentar pegar:
SELECT * FROM queue_items
WHERE cloud_status = 'PENDING'
AND locked_until < NOW()  # ← Não retorna "abc123" (locked!)
```

---

## ⚡ Estados e Transições

### **cloud_status**
```
PENDING → UPLOADING → UPLOADED ✅
   ↓
FAILED (retry depois)
```

### **local_status**
```
PENDING → PROCESSING → DONE ✅
   ↓
FAILED
```

### **connectivity_state**
```
UNKNOWN → ONLINE ↔ OFFLINE
             ↓
          DEGRADED
             ↓
       FORCED_OFFLINE
```

---

## 🎬 Como Rodar o Sistema Completo

### **Terminal 1: File Listener**
```bash
python main.py listener
```
Monitora `watch/` e registra novos arquivos

### **Terminal 2: Connectivity Manager**
```bash
python main.py connectivity-manager
```
Verifica se está online/offline

### **Terminal 3: Cloud Worker** (se online)
```bash
python main.py cloud-worker
```
Envia para nuvem quando ONLINE

### **Terminal 4: Local Worker** (se offline)
```bash
python main.py local-worker
```
Processa localmente quando OFFLINE

### **Testar:**
```bash
# Copiar imagem
cp test.jpg watch/

# Ver status
python main.py status
```

---

## 🐛 Por Que o Teste Falhou?

O teste falhou porque você apenas **criou o registro no banco**, mas **não rodou o worker**!

```python
# Isso APENAS cria registro no banco:
repo.upsert_item('test-local-1', 'watch/test_image.jpg', ...)

# Para PROCESSAR, precisa rodar o worker:
worker.run()  # ← Isso que processa!
```

---

## ✅ Como Testar Corretamente

### **Opção 1: Processar 1 Item Manualmente**

```python
from local_processing.worker import LocalWorker
from db.repository import QueueRepository
import yaml

# Carregar config
config = yaml.safe_load(open('config/config.yaml'))

# Criar worker
worker = LocalWorker(config)

# Pegar itens pendentes
items = worker.repository.get_pending_local(limit=1)

if items:
    # Processar primeiro item
    worker._process_item(items[0])
    print(f"✅ Item processado!")
else:
    print("Nenhum item pendente")
```

### **Opção 2: Rodar Worker em Loop**

```bash
# Setar modo offline
python -c "from db.repository import QueueRepository; repo = QueueRepository('./db/miqa.db'); repo.set_system_state('connectivity_state', 'OFFLINE')"

# Rodar worker (Ctrl+C para parar)
python main.py local-worker
```

---

## 📁 Estrutura de Arquivos

```
Backend_local/
├── watch/                    # Imagens chegam aqui
│   └── test_image.jpg
├── db/
│   └── miqa.db              # SQLite (fonte da verdade)
├── results/                  # Resultados locais
│   └── abc123...json        # Criado pelo local_worker
├── edge/
│   └── listener.py          # Monitora watch/
├── connectivity/
│   └── manager.py           # Verifica online/offline
├── cloud_client/
│   └── worker.py            # Envia para nuvem
├── local_processing/
│   ├── worker.py            # Processa localmente
│   └── miqa_core.py         # Algoritmo MIQA
└── main.py                  # CLI para rodar tudo
```

---

## 🎯 Resumo

1. **File Listener** detecta imagens e registra no SQLite
2. **SQLite** é a fila central (fonte da verdade)
3. **Connectivity Manager** monitora se está online/offline
4. **Cloud Worker** processa quando ONLINE
5. **Local Worker** processa quando OFFLINE
6. Todos se comunicam via SQLite (não há comunicação direta)

**É como uma orquestra:** cada músico (worker) toca sua parte olhando para a partitura (SQLite)! 🎵

---

**Última atualização:** 2026-01-08 17:45

python -c "from db.repository import QueueRepository; repo = QueueRepository('./db/miqa.db'); repo.set_system_state('connectivity_state', 'ONLINE'); print('✅ Estado setado para ONLINE')"