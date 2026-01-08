# 🧪 TESTING - Backend Local MIQA

Documento de testes para validar cada tarefa implementada.

---

## 🎯 Objetivo

Validar cada componente do sistema conforme é implementado, garantindo que funciona corretamente antes de prosseguir para a próxima tarefa.

---

## ✅ Tarefa 1: Bootstrap - TESTES

### 1.1 Verificar Estrutura de Pastas

```bash
# Verificar se todas as pastas foram criadas
ls -la

# Deve mostrar:
# edge/
# cloud_client/
# local_processing/
# metrics/
# db/
# connectivity/
# config/
# utils/
# tests/
# results/
# logs/
# watch/
```

**Status:** ✅ PASSOU

---

### 1.2 Verificar Dependências

```bash
# Instalar dependências
pip install -r requirements.txt

# Verificar se instalou corretamente
pip list | grep watchdog
pip list | grep httpx
pip list | grep pydantic
pip list | grep click
```

**Resultado Esperado:**
```
watchdog       6.0.0
httpx          0.25.0+
pydantic       2.0.0+
click          8.1.0+
```

**Status:** ✅ PASSOU

---

### 1.3 Verificar Configuração

```bash
# Verificar se config.yaml existe
cat config/config.yaml

# Verificar se tem as chaves principais
grep "device_id" config/config.yaml
grep "mode" config/config.yaml
grep "api_url" config/config.yaml
```

**Resultado Esperado:**
```
device_id: "hospital-device-001"
mode: "AUTO"
api_url: "https://miqaback-production.up.railway.app"
```

**Status:** ✅ PASSOU

---

### 1.4 Verificar CLI

```bash
# Testar se CLI funciona
python main.py --help

# Deve mostrar todos os comandos
python main.py --version
```

**Resultado Esperado:**
```
Usage: main.py [OPTIONS] COMMAND [ARGS]...

Commands:
  cloud-worker
  connectivity-manager
  dicom-receiver
  init-db
  listener
  local-worker
  metrics-exporter
  start
  status
```

**Status:** ✅ PASSOU

---

### 1.5 Verificar Logging

```python
# Testar logging
python -c "
import yaml
from utils.logging_config import setup_logging

with open('config/config.yaml') as f:
    config = yaml.safe_load(f)

logger = setup_logging(config)
logger.info('Teste de logging')
logger.error('Teste de erro')
"

# Verificar se criou arquivo de log
cat logs/miqa.log
```

**Resultado Esperado:**
```json
{"timestamp": "2026-01-08T...", "level": "INFO", "device_id": "hospital-device-001", "message": "Teste de logging"}
{"timestamp": "2026-01-08T...", "level": "ERROR", "device_id": "hospital-device-001", "message": "Teste de erro"}
```

**Status:** ✅ PASSOU

---

## 🗄️ Tarefa 2: SQLite - TESTES

### 2.1 Verificar Migrations

```bash
# Inicializar banco de dados
python main.py init-db

# Verificar se criou o arquivo
ls -la db/miqa.db

# Verificar tabelas criadas
sqlite3 db/miqa.db ".tables"
```

**Resultado Esperado:**
```
migrations
queue_items
system_state
metrics_events
```

**Status:** ⏳ PENDENTE

---

### 2.2 Verificar Schema

```bash
# Ver schema da tabela queue_items
sqlite3 db/miqa.db ".schema queue_items"
```

**Resultado Esperado:**
```sql
CREATE TABLE queue_items (
    item_uid TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    source_type TEXT NOT NULL,
    ...
);
```

**Status:** ⏳ PENDENTE

---

### 2.3 Testar Repository

```python
# Testar operações básicas
python -c "
from db.repository import QueueRepository

repo = QueueRepository('./db/miqa.db')

# Inserir item
repo.upsert_item(
    item_uid='test-123',
    path='/tmp/test.jpg',
    source_type='LISTENER',
    meta={'modality': 'mri'}
)

# Buscar itens pendentes
items = repo.get_pending_cloud()
print(f'Itens pendentes: {len(items)}')

# Verificar estado do sistema
state = repo.get_system_state('connectivity_state')
print(f'Estado: {state}')
"
```

**Resultado Esperado:**
```
Itens pendentes: 1
Estado: UNKNOWN
```

**Status:** ⏳ PENDENTE

---

### 2.4 Testar Concorrência

```python
# Testar lock de concorrência
python -c "
from db.repository import QueueRepository
import time

repo = QueueRepository('./db/miqa.db')

# Inserir item
repo.upsert_item('test-456', '/tmp/test2.jpg', 'LISTENER', {})

# Marcar como uploading (lock)
repo.mark_cloud_uploading('test-456', lock_duration_minutes=1)

# Tentar pegar novamente (não deve retornar)
items = repo.get_pending_cloud()
print(f'Itens disponíveis: {len(items)}')  # Deve ser 0

# Esperar lock expirar
time.sleep(65)
items = repo.get_pending_cloud()
print(f'Após expirar: {len(items)}')  # Deve ser 1
"
```

**Resultado Esperado:**
```
Itens disponíveis: 0
Após expirar: 1
```

**Status:** ⏳ PENDENTE

---

## 📁 Tarefa 3: Ingestão - TESTES

### 3.1 Testar File Stability

```python
# Testar verificação de arquivo estável
python -c "
from utils.file_stability import is_file_stable
from pathlib import Path
import time

# Criar arquivo de teste
test_file = Path('watch/test_mri.jpg')
test_file.parent.mkdir(exist_ok=True)

# Escrever arquivo
with open(test_file, 'wb') as f:
    f.write(b'test data')

# Verificar se está estável
stable = is_file_stable(test_file)
print(f'Arquivo estável: {stable}')  # Deve ser True

test_file.unlink()  # Limpar
"
```

**Resultado Esperado:**
```
Arquivo estável: True
```

**Status:** ⏳ PENDENTE

---

### 3.2 Testar Listener

```bash
# Terminal 1: Iniciar listener
python main.py listener

# Terminal 2: Copiar arquivo para pasta watch
cp test_image.jpg watch/

# Verificar logs
tail -f logs/miqa.log | grep "Arquivo detectado"

# Verificar se foi registrado no banco
sqlite3 db/miqa.db "SELECT * FROM queue_items;"
```

**Resultado Esperado:**
```
Logs mostram: "Arquivo detectado: watch/test_image.jpg"
Banco mostra: 1 item com source_type='LISTENER'
```

**Status:** ⏳ PENDENTE

---

### 3.3 Testar Geração de UID

```python
# Testar geração de UID
python -c "
from edge.listener import ImageFileHandler
from pathlib import Path

handler = ImageFileHandler(None)

# Criar arquivo de teste
test_file = Path('watch/test.jpg')
with open(test_file, 'wb') as f:
    f.write(b'test data')

# Gerar UID
uid = handler._generate_uid(test_file)
print(f'UID: {uid}')
print(f'Tamanho: {len(uid)}')  # Deve ser 64 (SHA256)

test_file.unlink()
"
```

**Resultado Esperado:**
```
UID: a1b2c3d4e5f6...
Tamanho: 64
```

**Status:** ⏳ PENDENTE

---

## 🌐 Tarefa 5: Connectivity - TESTES

### 5.1 Testar Healthcheck

```python
# Testar healthcheck manual
python -c "
import asyncio
import httpx

async def test():
    url = 'https://miqaback-production.up.railway.app/health'
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=3)
        print(f'Status: {response.status_code}')
        print(f'Body: {response.text}')

asyncio.run(test())
"
```

**Resultado Esperado:**
```
Status: 200
Body: {"status": "healthy"}
```

**Status:** ⏳ PENDENTE

---

### 5.2 Testar Connectivity Manager

```bash
# Terminal 1: Iniciar connectivity manager
python main.py connectivity-manager

# Terminal 2: Verificar estado no banco
watch -n 1 "sqlite3 db/miqa.db \"SELECT * FROM system_state WHERE key='connectivity_state';\""
```

**Resultado Esperado:**
```
Estado muda de UNKNOWN -> ONLINE (se API estiver acessível)
Estado muda de UNKNOWN -> OFFLINE (se API não estiver acessível)
```

**Status:** ⏳ PENDENTE

---

### 5.3 Testar Histerese

```python
# Simular falhas e sucessos
python -c "
from connectivity.manager import ConnectivityManager
import yaml

with open('config/config.yaml') as f:
    config = yaml.safe_load(f)

manager = ConnectivityManager(config)

# Simular 3 falhas
for i in range(3):
    manager.recent_checks.append(('FAILED', None))

manager._update_state()
print(f'Estado após 3 falhas: {manager.current_state}')  # Deve ser OFFLINE

# Simular 3 sucessos
for i in range(3):
    manager.recent_checks.append(('SUCCESS', 100))

manager._update_state()
print(f'Estado após 3 sucessos: {manager.current_state}')  # Deve ser ONLINE
"
```

**Resultado Esperado:**
```
Estado após 3 falhas: OFFLINE
Estado após 3 sucessos: ONLINE
```

**Status:** ⏳ PENDENTE

---

## ☁️ Tarefa 6: Cloud Worker - TESTES

### 6.1 Testar Upload

```python
# Testar upload manual
python -c "
import asyncio
import httpx
from pathlib import Path

async def test():
    url = 'https://miqaback-production.up.railway.app/api/v1/miqa/analyze'
    
    # Criar imagem de teste
    test_file = Path('watch/test_image.jpg')
    with open(test_file, 'wb') as f:
        f.write(b'fake image data')
    
    async with httpx.AsyncClient() as client:
        with open(test_file, 'rb') as f:
            files = {'file': f}
            data = {'modality': 'mri', 'device_id': 'test'}
            headers = {'Idempotency-Key': 'test-123'}
            
            response = await client.post(url, files=files, data=data, headers=headers, timeout=30)
            print(f'Status: {response.status_code}')
    
    test_file.unlink()

asyncio.run(test())
"
```

**Resultado Esperado:**
```
Status: 200 (ou 400 se imagem inválida)
```

**Status:** ⏳ PENDENTE

---

### 6.2 Testar Cloud Worker

```bash
# Preparar: Inserir item no banco
sqlite3 db/miqa.db "
INSERT INTO queue_items (item_uid, path, source_type, cloud_status, meta_modality)
VALUES ('test-789', 'watch/test.jpg', 'LISTENER', 'PENDING', 'mri');
"

# Criar arquivo
echo "test" > watch/test.jpg

# Iniciar cloud worker
python main.py cloud-worker

# Verificar logs
tail -f logs/miqa.log | grep "Upload"

# Verificar status no banco
sqlite3 db/miqa.db "SELECT item_uid, cloud_status FROM queue_items WHERE item_uid='test-789';"
```

**Resultado Esperado:**
```
Logs: "✅ Upload OK: test-789"
Banco: cloud_status='UPLOADED'
```

**Status:** ⏳ PENDENTE

---

## 💻 Tarefa 7: Local Worker - TESTES

### 7.1 Verificar Código Copiado

```bash
# Verificar se arquivos foram copiados
ls -la local_processing/

# Deve ter:
# miqa_core.py
# wingsai_core.py
# heuristics/
# preprocessing/
```

**Status:** ⏳ PENDENTE

---

### 7.2 Testar Processamento Local

```python
# Testar processamento
python -c "
from local_processing.worker import LocalWorker
import yaml

with open('config/config.yaml') as f:
    config = yaml.safe_load(f)

worker = LocalWorker(config)

# Criar item de teste no banco
from db.repository import QueueRepository
repo = QueueRepository(config['database']['path'])

repo.upsert_item('test-local-1', 'watch/test_image.jpg', 'LISTENER', {'modality': 'mri'})
"
# Processar
# (worker.run() é bloqueante, então testar manualmente)

```

**Status:** ⏳ PENDENTE

---

### 7.3 Testar Resultado Local

```bash
# Verificar se resultado foi salvo
ls -la results/

# Deve ter arquivo JSON
cat results/test-local-1.json
```

**Resultado Esperado:**
```json
{
  "score": 85.5,
  "features": {...},
  "status": "success"
}
```

**Status:** ⏳ PENDENTE

---

## 📊 Tarefa 8: Métricas - TESTES

### 8.1 Testar Registro de Métrica

```python
# Testar registro
python -c "
from metrics.collector import MetricsCollector

collector = MetricsCollector('test-device')

# Registrar métricas
collector.increment('items_detected_total', {'source': 'listener'})
collector.gauge('queue_pending_count', 5, {'type': 'cloud'})

print('Métricas registradas!')
"

# Verificar no banco
sqlite3 db/miqa.db "SELECT * FROM metrics_events;"
```

**Resultado Esperado:**
```
2 linhas na tabela metrics_events
```

**Status:** ⏳ PENDENTE

---

## 🔄 Teste de Integração Completo

### Cenário: Fluxo Completo Online

```bash
# 1. Inicializar banco
python main.py init-db

# 2. Iniciar todos os serviços (em terminais separados)
python main.py listener
python main.py connectivity-manager
python main.py cloud-worker

# 3. Copiar imagem para pasta watch
cp test_image.jpg watch/

# 4. Aguardar processamento (verificar logs)
tail -f logs/miqa.log

# 5. Verificar resultado
sqlite3 db/miqa.db "SELECT item_uid, cloud_status FROM queue_items;"
```

**Resultado Esperado:**
```
1. Listener detecta arquivo
2. Connectivity manager marca ONLINE
3. Cloud worker envia para API
4. Status muda para UPLOADED
```

**Status:** ⏳ PENDENTE

---

### Cenário: Fluxo Completo Offline

```bash
# 1. Configurar modo offline
# Editar config.yaml: mode: "FORCED_OFFLINE"

# 2. Iniciar serviços
python main.py listener
python main.py local-worker

# 3. Copiar imagem
cp test_image.jpg watch/

# 4. Verificar processamento local
ls -la results/
```

**Resultado Esperado:**
```
1. Listener detecta arquivo
2. Local worker processa
3. Resultado salvo em results/
4. Status: local_status='DONE'
```

**Status:** ⏳ PENDENTE

---

## 📋 Checklist de Validação

### Tarefa 1: Bootstrap
- [x] Estrutura de pastas criada
- [x] Dependências instaladas
- [x] Configuração criada
- [x] CLI funciona
- [x] Logging funciona

### Tarefa 2: SQLite
- [ ] Banco criado
- [ ] Tabelas criadas
- [ ] Repository funciona
- [ ] Lock funciona
- [ ] Idempotência funciona

### Tarefa 3: Ingestão
- [ ] File stability funciona
- [ ] Listener detecta arquivos
- [ ] UID gerado corretamente
- [ ] Item registrado no banco

### Tarefa 4: Arquivo Parcial
- [ ] Verificação de estabilidade funciona
- [ ] Timeout funciona
- [ ] Integração com listener funciona

### Tarefa 5: Connectivity
- [ ] Healthcheck funciona
- [ ] Estados funcionam
- [ ] Histerese funciona
- [ ] Estado salvo no banco

### Tarefa 6: Cloud Worker
- [ ] Upload funciona
- [ ] Idempotência funciona
- [ ] Retry funciona
- [ ] Status atualizado

### Tarefa 7: Local Worker
- [ ] Código copiado
- [ ] Processamento funciona
- [ ] Resultado salvo
- [ ] Status atualizado

### Tarefa 8: Métricas
- [ ] Registro funciona
- [ ] Labels corretos
- [ ] Persistência funciona

### Integração
- [ ] Fluxo online completo
- [ ] Fluxo offline completo
- [ ] Reconciliação funciona

---

## 🎯 Como Usar Este Documento

1. **Após implementar cada tarefa**, execute os testes correspondentes
2. **Marque como ✅ PASSOU** se funcionou
3. **Marque como ❌ FALHOU** se não funcionou e documente o erro
4. **Só prossiga para próxima tarefa** quando todos os testes passarem

---

**Última atualização:** 2026-01-08 14:40
