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
**Status:** Concluído

- [x] 3.1 Implementar detector de origem
  - [x] Classe `ImageDetector` com método `detect()`
  - [x] Suporte para `LISTENER` (pasta)
  - [x] Stub para `DICOM SCP` (não implementar ainda)

- [x] 3.2 Listener de pasta (edge/listener.py)
  - [x] Usar `watchdog` para monitorar diretório
  - [x] Eventos: `on_created`, `on_modified`, `on_moved`
  - [x] Varredura periódica (fallback a cada 30s)
  - [x] Filtrar apenas imagens: `.jpg`, `.png`, `.dcm`

- [x] 3.3 DICOM SCP (edge/dicom_receiver.py)
  - [x] Criar stub básico com `pynetdicom`
  - [x] Receber instância e salvar em pasta controlada
  - [x] Gerar `item_uid` a partir de `SOPInstanceUID`
  - [x] **STUB APENAS - não implementado completamente**

- [x] 3.4 Gerar `item_uid`
  - [x] Se DICOM: usar `SOPInstanceUID`
  - [x] Se arquivo comum: `sha256(conteúdo)` ou `sha256(tamanho + mtime + hash_parcial)`

- [x] 3.5 Registrar no SQLite
  - [x] Chamar `repository.upsert_item()` ao detectar arquivo

---

## ✅ Tarefa 4: Proteção Arquivo Parcial
**Status:** Concluído

- [x] 4.1 Implementar verificação "arquivo estável"
  - [x] Função: `is_file_stable(path, checks=5, interval=1.0)`
  - [x] Verificar tamanho e mtime em intervalos
  - [x] Retornar True apenas se não mudar por 5 verificações

- [x] 4.2 Implementar timeout
  - [x] Timeout máximo: 30 segundos
  - [x] Se não estabilizar, marcar como `FAILED` com erro "partial_file"

- [x] 4.3 Integrar com listener
  - [x] Só inserir no SQLite após arquivo estabilizar
  - [x] Ou inserir como `DETECTED` e promover para `READY` depois

---

## ✅ Tarefa 5: Connectivity Manager
**Status:** Concluído

- [x] 5.1 Implementar estados
  - [x] `ONLINE` - internet OK
  - [x] `OFFLINE` - sem internet
  - [x] `DEGRADED` - internet lenta/instável
  - [x] `FORCED_OFFLINE` - modo forçado offline

- [x] 5.2 Implementar healthcheck
  - [x] Endpoint: `GET /health` na API de produção
  - [x] Timeout: 3 segundos
  - [x] Periodicidade: a cada 10 segundos

- [x] 5.3 Implementar medição de latência
  - [x] Janela deslizante: últimos 10 checks
  - [x] Histerese: 3 falhas consecutivas para marcar OFFLINE
  - [x] Histerese: 3 sucessos consecutivos para marcar ONLINE

- [x] 5.4 Expor estado atual
  - [x] Criar tabela `system_state` no SQLite
  - [x] Campos: `key`, `value`, `updated_at`
  - [x] Chave: `connectivity_state` com valor `ONLINE|OFFLINE|DEGRADED|FORCED_OFFLINE`

- [x] 5.5 Implementar modo `FORCED_OFFLINE`
  - [x] Ler de `config.yaml`: `mode: FORCED_OFFLINE`
  - [x] Se ativo, sempre retornar `FORCED_OFFLINE`

---

## ✅ Tarefa 6: Cloud Worker
**Status:** Concluído

- [x] 6.1 Implementar cliente HTTP (cloud_client/sender.py)
  - [x] Usar `httpx` com async
  - [x] Configurar timeouts: connect=5s, read=30s
  - [x] Configurar retries: 3 tentativas com backoff exponencial
  - [x] Limite de concorrência: 5 uploads simultâneos

- [x] 6.2 Definir contrato de upload
  - [x] Endpoint: `POST /api/v1/miqa/analyze`
  - [x] Formato: multipart/form-data
  - [x] Campos: `file`, `modality`, `device_id`, `item_uid`

- [x] 6.3 Implementar seleção de itens
  - [x] Query: `cloud_status IN ('PENDING', 'FAILED') AND next_retry_at <= now() AND locked_until < now()`
  - [x] Ordenar por: `detected_at ASC` (FIFO)

- [x] 6.4 Implementar "claim" do item
  - [x] Marcar `cloud_status='UPLOADING'`
  - [x] Setar `locked_until = now() + 5 minutos`

- [x] 6.5 Implementar idempotência
  - [x] Header: `Idempotency-Key: {item_uid}`

- [x] 6.6 Atualizar SQLite conforme resultado
  - [x] Sucesso: `cloud_status='UPLOADED'`, salvar resultado
  - [x] Falha: `cloud_status='FAILED'`, incrementar `retry_count`, setar `next_retry_at`

- [x] 6.7 Respeitar Connectivity Manager
  - [x] Verificar `system_state.connectivity_state`
  - [x] Se `OFFLINE` ou `FORCED_OFFLINE`, não tentar enviar

---

## ✅ Tarefa 7: Local Worker
**Status:** Concluído

- [x] 7.1 Copiar código de processamento do projeto principal
  - [x] Copiar de: `fadex_medicina_projeto1/src/ml/`
  - [x] Colar em: `Backend_local/local_processing/`
  - [x] Arquivos copiados:
    - [x] `scoring/miqa_core.py`
    - [x] `scoring/wingsai_core.py`
    - [x] `scoring/heuristics/` (pasta completa)
    - [x] `scoring/preprocessing/` (pasta completa)

- [x] 7.2 Criar interface de processamento
  - [x] Função: `process_local(path: str, meta: dict) -> dict`
  - [x] Retornar: `{"score": float, "features": dict, "status": str}`

- [x] 7.3 Implementar seleção de itens
  - [x] Condição: `connectivity_state != 'ONLINE'` OU `mode == 'FORCED_OFFLINE'`
  - [x] Query: `local_status = 'PENDING' AND locked_until < now()`

- [x] 7.4 Persistir resultado local
  - [x] Salvar JSON em: `results/{item_uid}.json`
  - [x] Atualizar SQLite: `local_result_path`, `local_status='DONE'`

- [x] 7.5 Política de reconciliação
  - [x] Opção 1: "local é definitivo" - não enviar para nuvem depois
  - [x] Opção 2: "enviar para nuvem depois" - setar `cloud_status='PENDING'` quando voltar online
  - [x] **Decisão:** Implementar Opção 2 (enviar para nuvem quando voltar)

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
