1) **Bootstrap do projeto (estrutura e execução)**
- 1.1 Definir estrutura de pastas (`edge/`, `cloud_client/`, `local_processing/`, `metrics/`, `db/`, `config/`, `tests/`). 
- 1.2 Definir gerenciador de dependências (Poetry ou pip-tools) e travar versões. [vamos de pip]
- 1.3 Criar arquivo de configuração (YAML/TOML/ENV) com perfis: `AUTO` e `FORCED_OFFLINE`.
- 1.4 Criar entrypoint (CLI) para subir os serviços: `listener`, `dicom_receiver`, `connectivity_manager`, `cloud_worker`, `local_worker`, `metrics_exporter`. [aqui raul imagine que sao aquelas chamadas de linha de comando só que precisamos que todas funcionem para o sistema se chamar por assim tambem]
- 1.5 Padronizar logging estruturado (JSON) com `device_id` e `item_uid` em todas as linhas de log.

2) **Modelo de dados e fila no SQLite (fonte da verdade)** [ raul estudar o motivo]
- 2.1 Definir o esquema SQLite e migrations (ex.: Alembic ou migrações simples por versão). [vamos de migrations simples por enquanto. montar o script mas só precisaremos em producao]
- 2.2 Criar tabela `queue_items` com campos mínimos:
  - `item_uid` UNIQUE, `path`, `source_type`, `detected_at`
  - `cloud_status`, `local_status`, `decision`, `retry_count`, `next_retry_at`, `last_error`
  - `meta_modality`, `meta_device`, `meta_exam_type` (sempre minimizado).
- 2.3 Implementar acesso ao DB (repositório): `upsert_item`, `get_pending_cloud`, `get_pending_local`, `mark_*`.
- 2.4 Implementar lock de concorrência (por item) para evitar dois workers processarem o mesmo registro (ex.: `SELECT ... FOR UPDATE` não existe no SQLite; usar “claim” via update atômico com campo `locked_until`).
- 2.5 Implementar idempotência: garantir que reprocessos não gerem duplicatas (constraints + lógica de `upsert`).

3) **Ingestão de imagens no edge (origem)**
- 3.1 Implementar “detector” de origem: `LISTENER` (pasta) e stub para `DICOM SCP opcional`.
- 3.2 Listener de pasta:
  - 3.2.1 Monitorar diretório (watchdog/inotify) e também varredura periódica (fallback).
  - 3.2.2 Normalizar eventos (create, move, modify) para “novo arquivo candidato”.
- 3.3 DICOM SCP opcional (se você for implementar): [vamos deixar  o codigo basico pronto mas nao perca tempo aqui ainda pf. entrarei nisso em breve se der ruim no dia presencial]
  - 3.3.1 Definir biblioteca (pydicom + pynetdicom).
  - 3.3.2 Receber instâncias e salvar em diretório controlado.
  - 3.3.3 Gerar `item_uid` a partir de `SOPInstanceUID`.
- 3.4 Gerar `item_uid`:
  - 3.4.1 Se DICOM: `SOPInstanceUID`.
  - 3.4.2 Se arquivo comum: hash (sha256) do conteúdo ou hash incremental (tamanho + mtime + hash parcial com confirmação).
- 3.5 Registrar no SQLite via `upsert_item` assim que detectar.

4) **Proteção contra arquivo parcial (arquivo estável)** [raul, aqui o gpt pode implementar mas por favor estude este tema]
- 4.1 Implementar verificação “arquivo estável”:
  - checar tamanho e mtime em intervalos (ex.: 1s por 5 vezes) e só aceitar se não muda.
- 4.2 Implementar timeout para não travar item (se nunca estabiliza, marcar `FAILED` com erro “partial”).
- 4.3 Integrar com o listener: só inserir no SQLite como “pronto para processar” após estabilizar, ou inserir como `DETECTED` e depois promover para `READY`.

5) **Connectivity Manager (decisão online vs offline, e modo forçado)**
- 5.1 Implementar estados: `ONLINE`, `OFFLINE`, `DEGRADED`, `FORCED_OFFLINE`.
- 5.2 Implementar healthcheck periódico no endpoint (ex.: `GET /health`) com timeout curto.
- 5.3 Implementar medição de latência e janela deslizante de erros (histerese para evitar alternância rápida).
- 5.4 Expor o estado atual para os workers:
  - 5.4.1 via memória compartilhada (se monolítico) ou [faremos pelo 5.4.2]
  - 5.4.2 via SQLite (`system_state` table) para processos separados.
- 5.5 Implementar configuração que desativa permanentemente o online: `FORCED_OFFLINE`.

6) **Worker de envio para nuvem (Cloud Sender)**
- 6.1 Implementar cliente HTTP em Python (recomendado: `httpx`):
  - timeouts, retries controlados, limite de concorrência, TLS.
- 6.2 Definir contrato do upload: [ainda nao sei qual seria o melhor]
  - 6.2.1 multipart (arquivo + metadados) ou
  - 6.2.2 upload por URL pré-assinada (se existir).
- 6.3 Implementar seleção de itens pendentes:
  - pegar do SQLite `cloud_status = PENDING ou FAILED` e `next_retry_at <= now`.
- 6.4 Implementar “claim” do item (marcar `UPLOADING` e `locked_until`) antes de enviar.
- 6.5 Implementar idempotência no request (header `Idempotency-Key: item_uid`).
- 6.6 Atualizar SQLite conforme resultado:
  - sucesso: `cloud_status=UPLOADED` ou `ANALYZED` (se API já responde resultado)
  - falha: `cloud_status=FAILED`, incrementar `retry_count`, setar `next_retry_at`.
- 6.7 Respeitar Connectivity Manager:
  - se `OFFLINE` ou `FORCED_OFFLINE`, não tentar enviar e liberar item.

7) **Worker de processamento local (fallback)**
- 7.1 Definir interface do processamento local: função `process_local(path, meta) -> result`.
- 7.2 Implementar seleção de itens pendentes:
  - se `connectivity_state != ONLINE` ou se modo forçado offline.
- 7.3 Implementar “claim” do item para processamento local (similar ao cloud).
- 7.4 Persistir resultado local:
  - 7.4.1 salvar JSON/CSV por item em diretório criptografado, e [nao precisa ser criptografado ainda]
  - 7.4.2 registrar `local_result_path` e `local_status=DONE` no SQLite.
- 7.5 Definir política de reconciliação quando a internet volta:
  - 7.5.1 “local é definitivo” ou
  - 7.5.2 “enviar para nuvem depois mesmo assim”.
  - Implementar isso como regra que seta `cloud_status=PENDING` após `local_status=DONE` (se política permitir).

8) **Métricas e logs locais (geração)** [raul, me lista quais ja existem, qal url posso ver e vamos discutir essas pf?]
- 8.1 Definir quais métricas serão emitidas (counters/gauges):
  - itens detectados, fila pendente, processados local, enviados cloud, falhas, latência healthcheck.
- 8.2 Implementar camada de métricas:
  - 8.2.1 registrar métricas em memória e flush para arquivo, ou
  - 8.2.2 registrar métricas/eventos em SQLite (tabela `metrics_events`).
- 8.3 Garantir que métricas de local e cloud tenham labels consistentes:
  - `device_id`, `mode=local|cloud`, `modality`.

9) **Exportação de métricas: batch quando online vs retenção para coleta presencial** [vamos fazer essa parte juntos]
- 9.1 Implementar “exporter” que roda periodicamente:
  - se `ONLINE` e permitido, envia lote acumulado para `GW`.
  - se `OFFLINE`, só acumula.
- 9.2 Definir formato do batch:
  - 9.2.1 eventos JSON para um endpoint seu (mais flexível), ou
  - 9.2.2 formato aceito por um gateway de métricas.
- 9.3 Implementar deduplicação no envio do batch (marcar registros como “enviados” no SQLite).
- 9.4 Implementar modo “coleta presencial”:
  - 9.4.1 comando CLI para exportar tudo para um pendrive (zip com assinatura hash),
  - 9.4.2 relatório resumido (CSV) por período.

10) **Criptografia em repouso e proteção de segredos** [nao faremos ainda]
- 10.1 Definir estratégia:
  - 10.1.1 criptografia de partição/disco (preferível, operacional) ou
  - 10.1.2 criptografia de arquivos (ex.: libsodium) para resultados e metadados.
- 10.2 Implementar armazenamento seguro de chaves (variáveis de ambiente + arquivo protegido).
- 10.3 Implementar rotação simples (trocar chave em implantação).
- 10.4 Garantir que logs não contenham dados sensíveis (máscaras).

11) **Retenção e limpeza (higiene operacional)** [sem limpexa por  enquanto]
- 11.1 Política de retenção de imagens no edge (ex.: deletar após `cloud_status=UPLOADED` e prazo X).
- 11.2 Limpeza de resultados locais após exportação (quando aplicável).
- 11.3 Rotação de logs e limites de disco (evitar encher SD card do Raspberry).
- 11.4 Watchdog: reiniciar serviços travados e alertar via métrica.

12) **Testes e validação no hospital (piloto)**
- 12.1 Testes unitários do SQLite repository e máquina de estados.
- 12.2 Testes de “arquivo parcial” com simulação de escrita lenta.
- 12.3 Testes de queda e retorno de internet:
  - 12.3.1 simular OFFLINE -> processar local -> voltar ONLINE -> retomar cloud.
- 12.4 Teste de carga leve (taxa de exames esperada) e ver backlog.
- 12.5 Checklist de observabilidade: dashboards com fila, falhas, processamento local vs cloud.

13) **Melhoria futura: fechar o loop com o hospital (não necessário agora)**
- 13.1 Definir canal de retorno: HL7 ORU, FHIR Observation, ou DICOM SR.
- 13.2 Implementar “result publisher” (serviço separado) com auditoria e versionamento.
- 13.3 Validar com TI hospitalar e homologar integração no prontuário.

Se você quiser, eu transformo essa lista em um “backlog” já com **prioridade (P0/P1/P2)** e uma sugestão de “MVP em 2 dias no hospital” vs “produção em 4–6 semanas”.