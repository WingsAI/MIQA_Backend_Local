# 📋 TODO - Backend Local MIQA

## 🎯 Meta de Hoje: Tarefas 1-8

---

## ✅ Tarefa 1: Bootstrap do Projeto
**Status:** Concluído

- [x] 1.1 Criar estrutura de pastas
  - [x] `edge/` - Detecção e ingestão de imagens
  - [x] `cloud_client/` - Cliente HTTP para nuvem
  - [x] `local_processing/` - Processamento offline (código do projeto principal)
  - [x] `metrics/` - Sistema de métricas
  - [x] `db/` - SQLite e migrations
  - [x] `config/` - Arquivos de configuração
  - [x] `tests/` - Testes unitários

- [x] 1.2 Configurar pip e requirements.txt
  - [x] Travar versões das dependências
  - [x] Incluir: `watchdog`, `httpx`, `pydantic`, `alembic`

- [x] 1.3 Criar arquivo de configuração (config.yaml)
  - [x] Perfil `AUTO` - decide automaticamente online/offline
  - [x] Perfil `FORCED_OFFLINE` - sempre offline

- [x] 1.4 Criar CLI (main.py)
  - [x] Comando: `listener` - monitora pasta
  - [x] Comando: `dicom_receiver` - recebe DICOM (stub)
  - [x] Comando: `connectivity_manager` - gerencia estado de rede
  - [x] Comando: `cloud_worker` - envia para nuvem
  - [x] Comando: `local_worker` - processa localmente
  - [x] Comando: `metrics_exporter` - exporta métricas

- [x] 1.5 Configurar logging estruturado (JSON)
  - [x] Incluir `device_id` em todos os logs
  - [x] Incluir `item_uid` quando aplicável
  - [x] Formato: `{"timestamp": "...", "level": "...", "device_id": "...", "message": "..."}`

---

## ✅ Tarefa 2: Modelo de Dados SQLite
**Status:** Concluído

- [x] 2.1 Criar schema SQLite
  - [x] Script de migrations simples (versão)
  - [x] Arquivo: `db/migrations/001_initial.sql`

- [x] 2.2 Criar tabela `queue_items`
  ```sql
  - item_uid (TEXT UNIQUE PRIMARY KEY)
  - path (TEXT NOT NULL)
  - source_type (TEXT) -- 'LISTENER' ou 'DICOM'
  - detected_at (TIMESTAMP)
  - cloud_status (TEXT) -- 'PENDING', 'UPLOADING', 'UPLOADED', 'FAILED'
  - local_status (TEXT) -- 'PENDING', 'PROCESSING', 'DONE', 'FAILED'
  - decision (TEXT) -- 'CLOUD', 'LOCAL', 'BOTH'
  - retry_count (INTEGER DEFAULT 0)
  - next_retry_at (TIMESTAMP)
  - last_error (TEXT)
  - locked_until (TIMESTAMP) -- Para concorrência
  - meta_modality (TEXT)
  - meta_device (TEXT)
  - meta_exam_type (TEXT)
  - local_result_path (TEXT)
  - created_at (TIMESTAMP)
  - updated_at (TIMESTAMP)
  ```

- [x] 2.3 Criar repositório (db/repository.py)
  - [x] `upsert_item(item_uid, path, source_type, meta)`
  - [x] `get_pending_cloud()` - retorna itens para enviar
  - [x] `get_pending_local()` - retorna itens para processar localmente
  - [x] `mark_cloud_uploading(item_uid, locked_until)`
  - [x] `mark_cloud_uploaded(item_uid)`
  - [x] `mark_cloud_failed(item_uid, error, next_retry)`
  - [x] `mark_local_processing(item_uid, locked_until)`
  - [x] `mark_local_done(item_uid, result_path)`
  - [x] `mark_local_failed(item_uid, error)`

- [x] 2.4 Implementar lock de concorrência
  - [x] Usar `locked_until` com UPDATE atômico
  - [x] Exemplo: `UPDATE queue_items SET cloud_status='UPLOADING', locked_until=? WHERE item_uid=? AND locked_until < now()`

- [x] 2.5 Garantir idempotência
  - [x] UNIQUE constraint em `item_uid`
  - [x] Lógica de upsert (INSERT OR REPLACE)

---

## ✅ Tarefa 3: Ingestão de Imagens
**Status:** 🔴 Pendente

- [ ] 3.1 Implementar detector de origem
  - [ ] Classe `ImageDetector` com método `detect()`
  - [ ] Suporte para `LISTENER` (pasta)
  - [ ] Stub para `DICOM SCP` (não implementar ainda)

- [ ] 3.2 Listener de pasta (edge/listener.py)
  - [ ] Usar `watchdog` para monitorar diretório
  - [ ] Eventos: `on_created`, `on_modified`, `on_moved`
  - [ ] Varredura periódica (fallback a cada 30s)
  - [ ] Filtrar apenas imagens: `.jpg`, `.png`, `.dcm`

- [ ] 3.3 DICOM SCP (edge/dicom_receiver.py)
  - [ ] Criar stub básico com `pynetdicom`
  - [ ] Receber instância e salvar em pasta controlada
  - [ ] Gerar `item_uid` a partir de `SOPInstanceUID`
  - [ ] **NÃO IMPLEMENTAR COMPLETAMENTE AINDA**

- [ ] 3.4 Gerar `item_uid`
  - [ ] Se DICOM: usar `SOPInstanceUID`
  - [ ] Se arquivo comum: `sha256(conteúdo)` ou `sha256(tamanho + mtime + hash_parcial)`

- [ ] 3.5 Registrar no SQLite
  - [ ] Chamar `repository.upsert_item()` ao detectar arquivo

---

## ✅ Tarefa 4: Proteção Arquivo Parcial
**Status:** 🔴 Pendente

- [ ] 4.1 Implementar verificação "arquivo estável"
  - [ ] Função: `is_file_stable(path, checks=5, interval=1.0)`
  - [ ] Verificar tamanho e mtime em intervalos
  - [ ] Retornar True apenas se não mudar por 5 verificações

- [ ] 4.2 Implementar timeout
  - [ ] Timeout máximo: 30 segundos
  - [ ] Se não estabilizar, marcar como `FAILED` com erro "partial_file"

- [ ] 4.3 Integrar com listener
  - [ ] Só inserir no SQLite após arquivo estabilizar
  - [ ] Ou inserir como `DETECTED` e promover para `READY` depois

---

## ✅ Tarefa 5: Connectivity Manager
**Status:** 🔴 Pendente

- [ ] 5.1 Implementar estados
  - [ ] `ONLINE` - internet OK
  - [ ] `OFFLINE` - sem internet
  - [ ] `DEGRADED` - internet lenta/instável
  - [ ] `FORCED_OFFLINE` - modo forçado offline

- [ ] 5.2 Implementar healthcheck
  - [ ] Endpoint: `GET /health` na API de produção
  - [ ] Timeout: 3 segundos
  - [ ] Periodicidade: a cada 10 segundos

- [ ] 5.3 Implementar medição de latência
  - [ ] Janela deslizante: últimos 10 checks
  - [ ] Histerese: 3 falhas consecutivas para marcar OFFLINE
  - [ ] Histerese: 3 sucessos consecutivos para marcar ONLINE

- [ ] 5.4 Expor estado atual
  - [ ] Criar tabela `system_state` no SQLite
  - [ ] Campos: `key`, `value`, `updated_at`
  - [ ] Chave: `connectivity_state` com valor `ONLINE|OFFLINE|DEGRADED|FORCED_OFFLINE`

- [ ] 5.5 Implementar modo `FORCED_OFFLINE`
  - [ ] Ler de `config.yaml`: `mode: FORCED_OFFLINE`
  - [ ] Se ativo, sempre retornar `FORCED_OFFLINE`

---

## ✅ Tarefa 6: Cloud Worker
**Status:** 🔴 Pendente

- [ ] 6.1 Implementar cliente HTTP (cloud_client/sender.py)
  - [ ] Usar `httpx` com async
  - [ ] Configurar timeouts: connect=5s, read=30s
  - [ ] Configurar retries: 3 tentativas com backoff exponencial
  - [ ] Limite de concorrência: 5 uploads simultâneos

- [ ] 6.2 Definir contrato de upload
  - [ ] Endpoint: `POST /api/v1/miqa/analyze`
  - [ ] Formato: multipart/form-data
  - [ ] Campos: `file`, `modality`, `device_id`, `item_uid`

- [ ] 6.3 Implementar seleção de itens
  - [ ] Query: `cloud_status IN ('PENDING', 'FAILED') AND next_retry_at <= now() AND locked_until < now()`
  - [ ] Ordenar por: `detected_at ASC` (FIFO)

- [ ] 6.4 Implementar "claim" do item
  - [ ] Marcar `cloud_status='UPLOADING'`
  - [ ] Setar `locked_until = now() + 5 minutos`

- [ ] 6.5 Implementar idempotência
  - [ ] Header: `Idempotency-Key: {item_uid}`

- [ ] 6.6 Atualizar SQLite conforme resultado
  - [ ] Sucesso: `cloud_status='UPLOADED'`, salvar resultado
  - [ ] Falha: `cloud_status='FAILED'`, incrementar `retry_count`, setar `next_retry_at`

- [ ] 6.7 Respeitar Connectivity Manager
  - [ ] Verificar `system_state.connectivity_state`
  - [ ] Se `OFFLINE` ou `FORCED_OFFLINE`, não tentar enviar

---

## ✅ Tarefa 7: Local Worker
**Status:** 🔴 Pendente

- [ ] 7.1 Copiar código de processamento do projeto principal
  - [ ] Copiar de: `fadex_medicina_projeto1/src/ml/`
  - [ ] Colar em: `Backend_local/local_processing/`
  - [ ] Arquivos necessários:
    - [ ] `scoring/miqa_core.py`
    - [ ] `scoring/wingsai_core.py`
    - [ ] `scoring/heuristics/` (pasta completa)
    - [ ] `scoring/preprocessing/` (pasta completa)

- [ ] 7.2 Criar interface de processamento
  - [ ] Função: `process_local(path: str, meta: dict) -> dict`
  - [ ] Retornar: `{"score": float, "features": dict, "status": str}`

- [ ] 7.3 Implementar seleção de itens
  - [ ] Condição: `connectivity_state != 'ONLINE'` OU `mode == 'FORCED_OFFLINE'`
  - [ ] Query: `local_status = 'PENDING' AND locked_until < now()`

- [ ] 7.4 Persistir resultado local
  - [ ] Salvar JSON em: `results/{item_uid}.json`
  - [ ] Atualizar SQLite: `local_result_path`, `local_status='DONE'`

- [ ] 7.5 Política de reconciliação
  - [ ] Opção 1: "local é definitivo" - não enviar para nuvem depois
  - [ ] Opção 2: "enviar para nuvem depois" - setar `cloud_status='PENDING'` quando voltar online
  - [ ] **Decisão:** Implementar Opção 2 (enviar para nuvem quando voltar)

---

## ✅ Tarefa 8: Métricas e Logs
**Status:** 🔴 Pendente

- [ ] 8.1 Definir métricas
  - [ ] `items_detected_total` - total de itens detectados
  - [ ] `queue_pending_count` - itens na fila
  - [ ] `processed_local_total` - processados localmente
  - [ ] `sent_cloud_total` - enviados para nuvem
  - [ ] `failures_total` - falhas (por tipo)
  - [ ] `healthcheck_latency_ms` - latência do healthcheck

- [ ] 8.2 Implementar camada de métricas
  - [ ] Criar tabela `metrics_events` no SQLite
  - [ ] Campos: `timestamp`, `metric_name`, `value`, `labels` (JSON)
  - [ ] Função: `record_metric(name, value, labels)`

- [ ] 8.3 Garantir labels consistentes
  - [ ] Sempre incluir: `device_id`
  - [ ] Incluir quando aplicável: `mode` (local/cloud), `modality`

---

## 📌 Notas Importantes

### Dependências do Projeto Principal
Precisamos copiar do `fadex_medicina_projeto1`:
- `src/ml/scoring/miqa_core.py`
- `src/ml/scoring/wingsai_core.py`
- `src/ml/scoring/heuristics/` (completo)
- `src/ml/scoring/preprocessing/` (completo)

### Decisões Tomadas
- ✅ Gerenciador: pip (não Poetry)
- ✅ Migrations: simples por versão (não Alembic)
- ✅ Criptografia: não implementar ainda
- ✅ Limpeza: não implementar ainda
- ✅ DICOM SCP: apenas stub básico
- ✅ Reconciliação: enviar para nuvem quando voltar online

### Ordem de Implementação Sugerida
1. Tarefa 1 (Bootstrap) - 30min
2. Tarefa 2 (SQLite) - 1h
3. Tarefa 3 (Ingestão) - 1h
4. Tarefa 4 (Arquivo Parcial) - 30min
5. Tarefa 5 (Connectivity) - 1h
6. Tarefa 7 (Local Worker) - 1h30min (copiar código)
7. Tarefa 6 (Cloud Worker) - 1h
8. Tarefa 8 (Métricas) - 30min

**Total Estimado:** 7-8 horas

---

## 🚀 Próximos Passos (Após Tarefa 8)

- Tarefa 9: Exportação de métricas
- Tarefa 12: Testes e validação
- Deploy no hospital

---

**Última atualização:** 2026-01-08
