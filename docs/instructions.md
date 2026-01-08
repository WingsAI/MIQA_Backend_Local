# 🛠️ INSTRUCTIONS - Backend Local MIQA

## 📖 Guia de Implementação - Tarefas 1-8

Este documento contém instruções detalhadas de implementação para cada tarefa.

---

## 🎯 Tarefa 1: Bootstrap do Projeto

### 1.1 Criar Estrutura de Pastas

```bash
# Na raiz do Backend_local/
mkdir -p edge cloud_client local_processing metrics db/migrations config tests results
```

**Estrutura esperada:**
```
Backend_local/
├── edge/
├── cloud_client/
├── local_processing/
├── metrics/
├── db/
│   └── migrations/
├── config/
├── tests/
├── results/
└── docs/
```

### 1.2 Criar requirements.txt

```txt
# Core
python>=3.9

# Monitoramento de arquivos
watchdog>=3.0.0

# Cliente HTTP
httpx>=0.25.0

# Validação
pydantic>=2.0.0

# DICOM (stub)
pynetdicom>=2.0.0
pydicom>=2.4.0

# Processamento de imagem (do projeto principal)
numpy>=1.24.0,<2.0.0
opencv-python-headless>=4.8.0
scikit-learn>=1.3.0
scikit-image>=0.21.0
scipy>=1.11.0
joblib>=1.3.0

# Logging
python-json-logger>=2.0.0

# Utilitários
python-dateutil>=2.8.0
pyyaml>=6.0.0
```

### 1.3 Criar config.yaml

```yaml
# config/config.yaml

# Identificação do dispositivo
device_id: "hospital-device-001"

# Modo de operação
mode: "AUTO"  # AUTO ou FORCED_OFFLINE

# Diretórios
directories:
  watch: "./watch"        # Pasta monitorada
  results: "./results"    # Resultados locais
  temp: "./temp"         # Arquivos temporários

# Banco de dados
database:
  path: "./db/miqa.db"

# Cloud
cloud:
  enabled: true
  api_url: "https://miqaback-production.up.railway.app"
  healthcheck_url: "https://miqaback-production.up.railway.app/health"
  healthcheck_interval: 10  # segundos
  healthcheck_timeout: 3    # segundos
  upload_timeout: 30        # segundos
  max_retries: 3
  retry_backoff: 2.0        # multiplicador

# Connectivity
connectivity:
  offline_threshold: 3      # falhas consecutivas para marcar OFFLINE
  online_threshold: 3       # sucessos consecutivos para marcar ONLINE
  degraded_latency_ms: 1000 # latência para marcar DEGRADED

# Workers
workers:
  cloud_worker_interval: 5  # segundos
  local_worker_interval: 5  # segundos
  max_concurrent_uploads: 5
  max_concurrent_processing: 2

# File stability
file_stability:
  checks: 5                 # número de verificações
  interval: 1.0             # segundos entre verificações
  timeout: 30               # timeout máximo

# Logging
logging:
  level: "INFO"
  format: "json"
  file: "./logs/miqa.log"
```

### 1.4 Criar CLI (main.py)

```python
# main.py
import click
import asyncio
import logging
from pathlib import Path

@click.group()
def cli():
    """Backend Local MIQA - Sistema de processamento offline"""
    pass

@cli.command()
def listener():
    """Monitora pasta e detecta novas imagens"""
    from edge.listener import FileListener
    click.echo("🔍 Iniciando listener...")
    listener = FileListener()
    listener.start()

@cli.command()
def dicom_receiver():
    """Recebe imagens via DICOM SCP (stub)"""
    from edge.dicom_receiver import DICOMReceiver
    click.echo("📡 Iniciando DICOM receiver...")
    receiver = DICOMReceiver()
    receiver.start()

@cli.command()
def connectivity_manager():
    """Gerencia estado de conectividade"""
    from connectivity.manager import ConnectivityManager
    click.echo("🌐 Iniciando connectivity manager...")
    manager = ConnectivityManager()
    asyncio.run(manager.run())

@cli.command()
def cloud_worker():
    """Envia imagens para nuvem"""
    from cloud_client.worker import CloudWorker
    click.echo("☁️ Iniciando cloud worker...")
    worker = CloudWorker()
    asyncio.run(worker.run())

@cli.command()
def local_worker():
    """Processa imagens localmente"""
    from local_processing.worker import LocalWorker
    click.echo("💻 Iniciando local worker...")
    worker = LocalWorker()
    worker.run()

@cli.command()
def metrics_exporter():
    """Exporta métricas"""
    from metrics.exporter import MetricsExporter
    click.echo("📊 Iniciando metrics exporter...")
    exporter = MetricsExporter()
    exporter.run()

@cli.command()
def init_db():
    """Inicializa banco de dados"""
    from db.migrations import run_migrations
    click.echo("🗄️ Inicializando banco de dados...")
    run_migrations()
    click.echo("✅ Banco de dados inicializado!")

if __name__ == "__main__":
    cli()
```

### 1.5 Configurar Logging

```python
# utils/logging_config.py
import logging
import json
from datetime import datetime
from pathlib import Path

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "device_id": getattr(record, 'device_id', 'unknown'),
            "item_uid": getattr(record, 'item_uid', None),
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)

def setup_logging(config):
    log_file = Path(config['logging']['file'])
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    handler = logging.FileHandler(log_file)
    handler.setFormatter(JSONFormatter())
    
    logger = logging.getLogger()
    logger.setLevel(config['logging']['level'])
    logger.addHandler(handler)
    
    # Console handler
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logger.addHandler(console)
    
    return logger
```

---

## 🗄️ Tarefa 2: Modelo de Dados SQLite

### 2.1 Script de Migration

```sql
-- db/migrations/001_initial.sql

-- Tabela principal de fila
CREATE TABLE IF NOT EXISTS queue_items (
    item_uid TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    source_type TEXT NOT NULL,  -- 'LISTENER' ou 'DICOM'
    detected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Status de processamento
    cloud_status TEXT DEFAULT 'PENDING',  -- PENDING, UPLOADING, UPLOADED, FAILED
    local_status TEXT DEFAULT 'PENDING',  -- PENDING, PROCESSING, DONE, FAILED
    decision TEXT,  -- CLOUD, LOCAL, BOTH
    
    -- Controle de retry
    retry_count INTEGER DEFAULT 0,
    next_retry_at TIMESTAMP,
    last_error TEXT,
    
    -- Lock de concorrência
    locked_until TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Metadados
    meta_modality TEXT,
    meta_device TEXT,
    meta_exam_type TEXT,
    
    -- Resultado local
    local_result_path TEXT,
    
    -- Auditoria
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_cloud_status ON queue_items(cloud_status, next_retry_at, locked_until);
CREATE INDEX IF NOT EXISTS idx_local_status ON queue_items(local_status, locked_until);
CREATE INDEX IF NOT EXISTS idx_detected_at ON queue_items(detected_at);

-- Tabela de estado do sistema
CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Inserir estado inicial
INSERT OR IGNORE INTO system_state (key, value) VALUES ('connectivity_state', 'UNKNOWN');

-- Tabela de métricas
CREATE TABLE IF NOT EXISTS metrics_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metric_name TEXT NOT NULL,
    value REAL NOT NULL,
    labels TEXT,  -- JSON
    device_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics_events(metric_name);
```

### 2.2 Runner de Migrations

```python
# db/migrations/__init__.py
import sqlite3
from pathlib import Path

def run_migrations(db_path="./db/miqa.db"):
    """Executa migrations simples por versão"""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Criar tabela de controle de migrations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS migrations (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Verificar versão atual
    cursor.execute("SELECT MAX(version) FROM migrations")
    current_version = cursor.execute("SELECT MAX(version) FROM migrations").fetchone()[0] or 0
    
    # Aplicar migrations pendentes
    migrations_dir = Path(__file__).parent
    for migration_file in sorted(migrations_dir.glob("*.sql")):
        version = int(migration_file.stem.split("_")[0])
        
        if version > current_version:
            print(f"Aplicando migration {version}...")
            with open(migration_file) as f:
                cursor.executescript(f.read())
            cursor.execute("INSERT INTO migrations (version) VALUES (?)", (version,))
            conn.commit()
            print(f"✅ Migration {version} aplicada!")
    
    conn.close()
    print("✅ Todas as migrations aplicadas!")
```

### 2.3 Repository

```python
# db/repository.py
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json

class QueueRepository:
    def __init__(self, db_path="./db/miqa.db"):
        self.db_path = db_path
    
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def upsert_item(self, item_uid: str, path: str, source_type: str, meta: Dict):
        """Insere ou atualiza item na fila"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO queue_items (
                item_uid, path, source_type, 
                meta_modality, meta_device, meta_exam_type
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_uid) DO UPDATE SET
                path = excluded.path,
                updated_at = CURRENT_TIMESTAMP
        """, (
            item_uid, path, source_type,
            meta.get('modality'), meta.get('device'), meta.get('exam_type')
        ))
        
        conn.commit()
        conn.close()
    
    def get_pending_cloud(self, limit=10) -> List[Dict]:
        """Retorna itens pendentes para envio à nuvem"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute("""
            SELECT * FROM queue_items
            WHERE cloud_status IN ('PENDING', 'FAILED')
            AND (next_retry_at IS NULL OR next_retry_at <= ?)
            AND locked_until < ?
            ORDER BY detected_at ASC
            LIMIT ?
        """, (now, now, limit))
        
        items = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return items
    
    def get_pending_local(self, limit=10) -> List[Dict]:
        """Retorna itens pendentes para processamento local"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        cursor.execute("""
            SELECT * FROM queue_items
            WHERE local_status = 'PENDING'
            AND locked_until < ?
            ORDER BY detected_at ASC
            LIMIT ?
        """, (now, limit))
        
        items = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return items
    
    def mark_cloud_uploading(self, item_uid: str, lock_duration_minutes=5):
        """Marca item como sendo enviado para nuvem"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        locked_until = (datetime.now() + timedelta(minutes=lock_duration_minutes)).isoformat()
        
        cursor.execute("""
            UPDATE queue_items
            SET cloud_status = 'UPLOADING',
                locked_until = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE item_uid = ?
        """, (locked_until, item_uid))
        
        conn.commit()
        conn.close()
    
    def mark_cloud_uploaded(self, item_uid: str):
        """Marca item como enviado com sucesso"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE queue_items
            SET cloud_status = 'UPLOADED',
                retry_count = 0,
                last_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE item_uid = ?
        """, (item_uid,))
        
        conn.commit()
        conn.close()
    
    def mark_cloud_failed(self, item_uid: str, error: str, retry_delay_minutes=5):
        """Marca item como falha no envio"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        next_retry = (datetime.now() + timedelta(minutes=retry_delay_minutes)).isoformat()
        
        cursor.execute("""
            UPDATE queue_items
            SET cloud_status = 'FAILED',
                retry_count = retry_count + 1,
                last_error = ?,
                next_retry_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE item_uid = ?
        """, (error, next_retry, item_uid))
        
        conn.commit()
        conn.close()
    
    def mark_local_processing(self, item_uid: str, lock_duration_minutes=10):
        """Marca item como sendo processado localmente"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        locked_until = (datetime.now() + timedelta(minutes=lock_duration_minutes)).isoformat()
        
        cursor.execute("""
            UPDATE queue_items
            SET local_status = 'PROCESSING',
                locked_until = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE item_uid = ?
        """, (locked_until, item_uid))
        
        conn.commit()
        conn.close()
    
    def mark_local_done(self, item_uid: str, result_path: str):
        """Marca item como processado localmente com sucesso"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE queue_items
            SET local_status = 'DONE',
                local_result_path = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE item_uid = ?
        """, (result_path, item_uid))
        
        conn.commit()
        conn.close()
    
    def mark_local_failed(self, item_uid: str, error: str):
        """Marca item como falha no processamento local"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE queue_items
            SET local_status = 'FAILED',
                last_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE item_uid = ?
        """, (error, item_uid))
        
        conn.commit()
        conn.close()
    
    def get_system_state(self, key: str) -> Optional[str]:
        """Retorna valor do estado do sistema"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT value FROM system_state WHERE key = ?", (key,))
        row = cursor.fetchone()
        
        conn.close()
        return row['value'] if row else None
    
    def set_system_state(self, key: str, value: str):
        """Define valor do estado do sistema"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO system_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        """, (key, value))
        
        conn.commit()
        conn.close()
```

---

## 📁 Tarefa 3: Ingestão de Imagens

### 3.1 File Listener

```python
# edge/listener.py
import time
import hashlib
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import logging

from db.repository import QueueRepository
from utils.file_stability import is_file_stable

logger = logging.getLogger(__name__)

class ImageFileHandler(FileSystemEventHandler):
    def __init__(self, repository: QueueRepository):
        self.repository = repository
        self.valid_extensions = {'.jpg', '.jpeg', '.png', '.dcm'}
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        path = Path(event.src_path)
        if path.suffix.lower() not in self.valid_extensions:
            return
        
        logger.info(f"Arquivo detectado: {path}")
        self._process_file(path)
    
    def _process_file(self, path: Path):
        # Verificar se arquivo está estável
        if not is_file_stable(path):
            logger.warning(f"Arquivo não estável, ignorando: {path}")
            return
        
        # Gerar item_uid
        item_uid = self._generate_uid(path)
        
        # Registrar no banco
        meta = {
            'modality': 'unknown',  # Será extraído depois
            'device': 'local',
            'exam_type': 'unknown'
        }
        
        self.repository.upsert_item(
            item_uid=item_uid,
            path=str(path),
            source_type='LISTENER',
            meta=meta
        )
        
        logger.info(f"Item registrado: {item_uid}")
    
    def _generate_uid(self, path: Path) -> str:
        """Gera UID baseado em hash do arquivo"""
        hasher = hashlib.sha256()
        with open(path, 'rb') as f:
            # Hash incremental para arquivos grandes
            for chunk in iter(lambda: f.read(4096), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

class FileListener:
    def __init__(self, watch_dir="./watch"):
        self.watch_dir = Path(watch_dir)
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.repository = QueueRepository()
        self.observer = Observer()
    
    def start(self):
        event_handler = ImageFileHandler(self.repository)
        self.observer.schedule(event_handler, str(self.watch_dir), recursive=True)
        self.observer.start()
        
        logger.info(f"Monitorando pasta: {self.watch_dir}")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.observer.stop()
        
        self.observer.join()
```

### 3.2 File Stability Check

```python
# utils/file_stability.py
import time
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def is_file_stable(path: Path, checks=5, interval=1.0, timeout=30) -> bool:
    """
    Verifica se arquivo está estável (não está sendo escrito)
    
    Args:
        path: Caminho do arquivo
        checks: Número de verificações
        interval: Intervalo entre verificações (segundos)
        timeout: Timeout máximo (segundos)
    
    Returns:
        True se arquivo está estável, False caso contrário
    """
    start_time = time.time()
    previous_size = None
    previous_mtime = None
    
    for i in range(checks):
        # Verificar timeout
        if time.time() - start_time > timeout:
            logger.warning(f"Timeout ao verificar estabilidade: {path}")
            return False
        
        try:
            stat = path.stat()
            current_size = stat.st_size
            current_mtime = stat.st_mtime
            
            if previous_size is not None:
                if current_size != previous_size or current_mtime != previous_mtime:
                    logger.debug(f"Arquivo ainda mudando: {path}")
                    previous_size = current_size
                    previous_mtime = current_mtime
                    time.sleep(interval)
                    continue
            
            previous_size = current_size
            previous_mtime = current_mtime
            time.sleep(interval)
            
        except FileNotFoundError:
            logger.warning(f"Arquivo não encontrado: {path}")
            return False
    
    logger.info(f"Arquivo estável: {path}")
    return True
```

---

## 🌐 Tarefa 5: Connectivity Manager

```python
# connectivity/manager.py
import asyncio
import httpx
import logging
from datetime import datetime
from collections import deque

from db.repository import QueueRepository

logger = logging.getLogger(__name__)

class ConnectivityManager:
    def __init__(self, config):
        self.config = config
        self.repository = QueueRepository()
        self.healthcheck_url = config['cloud']['healthcheck_url']
        self.healthcheck_interval = config['cloud']['healthcheck_interval']
        self.healthcheck_timeout = config['cloud']['healthcheck_timeout']
        
        # Histerese
        self.offline_threshold = config['connectivity']['offline_threshold']
        self.online_threshold = config['connectivity']['online_threshold']
        
        # Janela deslizante de resultados
        self.recent_checks = deque(maxlen=10)
        
        # Estado atual
        self.current_state = 'UNKNOWN'
    
    async def run(self):
        """Loop principal de verificação"""
        logger.info("Connectivity Manager iniciado")
        
        while True:
            await self._check_connectivity()
            await asyncio.sleep(self.healthcheck_interval)
    
    async def _check_connectivity(self):
        """Verifica conectividade com a nuvem"""
        try:
            async with httpx.AsyncClient() as client:
                start = datetime.now()
                response = await client.get(
                    self.healthcheck_url,
                    timeout=self.healthcheck_timeout
                )
                latency_ms = (datetime.now() - start).total_seconds() * 1000
                
                if response.status_code == 200:
                    self.recent_checks.append(('SUCCESS', latency_ms))
                    logger.debug(f"Healthcheck OK - {latency_ms:.0f}ms")
                else:
                    self.recent_checks.append(('FAILED', None))
                    logger.warning(f"Healthcheck failed - status {response.status_code}")
        
        except Exception as e:
            self.recent_checks.append(('FAILED', None))
            logger.warning(f"Healthcheck error: {e}")
        
        # Atualizar estado
        self._update_state()
    
    def _update_state(self):
        """Atualiza estado baseado em histerese"""
        # Contar sucessos e falhas recentes
        recent_list = list(self.recent_checks)
        if len(recent_list) < 3:
            return  # Aguardar mais dados
        
        last_3 = recent_list[-3:]
        successes = sum(1 for status, _ in last_3 if status == 'SUCCESS')
        failures = sum(1 for status, _ in last_3 if status == 'FAILED')
        
        # Histerese
        if failures >= self.offline_threshold:
            new_state = 'OFFLINE'
        elif successes >= self.online_threshold:
            new_state = 'ONLINE'
        else:
            new_state = self.current_state  # Manter estado atual
        
        # Atualizar se mudou
        if new_state != self.current_state:
            logger.info(f"Estado mudou: {self.current_state} -> {new_state}")
            self.current_state = new_state
            self.repository.set_system_state('connectivity_state', new_state)
```

---

## ☁️ Tarefa 6: Cloud Worker

```python
# cloud_client/worker.py
import asyncio
import httpx
import logging
from pathlib import Path

from db.repository import QueueRepository

logger = logging.getLogger(__name__)

class CloudWorker:
    def __init__(self, config):
        self.config = config
        self.repository = QueueRepository()
        self.api_url = config['cloud']['api_url']
        self.upload_timeout = config['cloud']['upload_timeout']
        self.max_retries = config['cloud']['max_retries']
    
    async def run(self):
        """Loop principal de envio"""
        logger.info("Cloud Worker iniciado")
        
        while True:
            # Verificar conectividade
            state = self.repository.get_system_state('connectivity_state')
            
            if state in ('OFFLINE', 'FORCED_OFFLINE'):
                logger.debug("Offline, aguardando...")
                await asyncio.sleep(10)
                continue
            
            # Processar itens pendentes
            items = self.repository.get_pending_cloud(limit=5)
            
            if not items:
                await asyncio.sleep(5)
                continue
            
            # Processar em paralelo
            tasks = [self._upload_item(item) for item in items]
            await asyncio.gather(*tasks)
    
    async def _upload_item(self, item):
        """Envia item para nuvem"""
        item_uid = item['item_uid']
        path = Path(item['path'])
        
        # Claim do item
        self.repository.mark_cloud_uploading(item_uid)
        
        try:
            async with httpx.AsyncClient() as client:
                with open(path, 'rb') as f:
                    files = {'file': f}
                    data = {
                        'modality': item['meta_modality'] or 'unknown',
                        'device_id': item['meta_device'] or 'unknown'
                    }
                    headers = {
                        'Idempotency-Key': item_uid
                    }
                    
                    response = await client.post(
                        f"{self.api_url}/api/v1/miqa/analyze",
                        files=files,
                        data=data,
                        headers=headers,
                        timeout=self.upload_timeout
                    )
                    
                    if response.status_code == 200:
                        self.repository.mark_cloud_uploaded(item_uid)
                        logger.info(f"✅ Upload OK: {item_uid}")
                    else:
                        error = f"HTTP {response.status_code}"
                        self.repository.mark_cloud_failed(item_uid, error)
                        logger.error(f"❌ Upload failed: {item_uid} - {error}")
        
        except Exception as e:
            error = str(e)
            self.repository.mark_cloud_failed(item_uid, error)
            logger.error(f"❌ Upload error: {item_uid} - {error}")
```

---

## 💻 Tarefa 7: Local Worker

### 7.1 Copiar Código do Projeto Principal

**Arquivos a copiar:**
```
Origem: fadex_medicina_projeto1/src/ml/
Destino: Backend_local/local_processing/

Copiar:
- scoring/miqa_core.py
- scoring/wingsai_core.py
- scoring/heuristics/ (pasta completa)
- scoring/preprocessing/ (pasta completa)
```

### 7.2 Worker Local

```python
# local_processing/worker.py
import logging
import json
from pathlib import Path
import cv2
import numpy as np

from db.repository import QueueRepository
from local_processing.miqa_core import MIQAAnalyzer

logger = logging.getLogger(__name__)

class LocalWorker:
    def __init__(self, config):
        self.config = config
        self.repository = QueueRepository()
        self.analyzer = MIQAAnalyzer()
        self.results_dir = Path(config['directories']['results'])
        self.results_dir.mkdir(parents=True, exist_ok=True)
    
    def run(self):
        """Loop principal de processamento"""
        logger.info("Local Worker iniciado")
        
        while True:
            # Verificar se deve processar localmente
            state = self.repository.get_system_state('connectivity_state')
            
            if state == 'ONLINE' and self.config['mode'] != 'FORCED_OFFLINE':
                # Online, não processar localmente
                time.sleep(10)
                continue
            
            # Processar itens pendentes
            items = self.repository.get_pending_local(limit=2)
            
            if not items:
                time.sleep(5)
                continue
            
            for item in items:
                self._process_item(item)
    
    def _process_item(self, item):
        """Processa item localmente"""
        item_uid = item['item_uid']
        path = Path(item['path'])
        
        # Claim do item
        self.repository.mark_local_processing(item_uid)
        
        try:
            # Carregar imagem
            image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            
            if image is None:
                raise ValueError("Não foi possível carregar imagem")
            
            # Processar
            result = self.analyzer.analyze(
                image,
                modality=item['meta_modality'] or 'mri'
            )
            
            # Salvar resultado
            result_path = self.results_dir / f"{item_uid}.json"
            with open(result_path, 'w') as f:
                json.dump(result, f, indent=2)
            
            # Marcar como concluído
            self.repository.mark_local_done(item_uid, str(result_path))
            logger.info(f"✅ Processamento local OK: {item_uid}")
            
            # Política de reconciliação: enviar para nuvem quando voltar online
            # (será implementado no cloud_worker)
        
        except Exception as e:
            error = str(e)
            self.repository.mark_local_failed(item_uid, error)
            logger.error(f"❌ Processamento local falhou: {item_uid} - {error}")
```

---

## 📊 Tarefa 8: Métricas

```python
# metrics/collector.py
import json
from datetime import datetime
from db.repository import QueueRepository

class MetricsCollector:
    def __init__(self, device_id):
        self.device_id = device_id
        self.repository = QueueRepository()
    
    def record_metric(self, name: str, value: float, labels: dict = None):
        """Registra métrica no SQLite"""
        conn = self.repository._get_conn()
        cursor = conn.cursor()
        
        labels = labels or {}
        labels['device_id'] = self.device_id
        
        cursor.execute("""
            INSERT INTO metrics_events (metric_name, value, labels, device_id)
            VALUES (?, ?, ?, ?)
        """, (name, value, json.dumps(labels), self.device_id))
        
        conn.commit()
        conn.close()
    
    def increment(self, name: str, labels: dict = None):
        """Incrementa contador"""
        self.record_metric(name, 1.0, labels)
    
    def gauge(self, name: str, value: float, labels: dict = None):
        """Registra gauge"""
        self.record_metric(name, value, labels)
```

---

## 🚀 Ordem de Execução

### Primeira Vez
```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Inicializar banco de dados
python main.py init-db

# 3. Criar pasta de monitoramento
mkdir watch

# 4. Iniciar todos os serviços (em terminais separados)
python main.py listener
python main.py connectivity-manager
python main.py cloud-worker
python main.py local-worker
```

### Teste
```bash
# Copiar imagem para pasta monitorada
cp test_image.jpg watch/

# Verificar logs
tail -f logs/miqa.log

# Verificar banco de dados
sqlite3 db/miqa.db "SELECT * FROM queue_items;"
```

---

**Próximo:** Implementar cada tarefa seguindo estas instruções! 🚀
