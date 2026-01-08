-- Migration 001: Initial Schema
-- Backend Local MIQA - Banco de dados SQLite

-- ============================================
-- Tabela principal de fila de processamento
-- ============================================
CREATE TABLE IF NOT EXISTS queue_items (
    -- Identificação
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
    
    -- Lock de concorrência (evita processamento duplicado)
    locked_until TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Metadados da imagem
    meta_modality TEXT,      -- mri, ct, us, etc
    meta_device TEXT,        -- ID do dispositivo de origem
    meta_exam_type TEXT,     -- Tipo de exame
    
    -- Resultado local
    local_result_path TEXT,  -- Caminho do JSON com resultado
    
    -- Auditoria
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_cloud_status 
    ON queue_items(cloud_status, next_retry_at, locked_until);

CREATE INDEX IF NOT EXISTS idx_local_status 
    ON queue_items(local_status, locked_until);

CREATE INDEX IF NOT EXISTS idx_detected_at 
    ON queue_items(detected_at);

CREATE INDEX IF NOT EXISTS idx_source_type 
    ON queue_items(source_type);

-- ============================================
-- Tabela de estado do sistema
-- ============================================
CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Inserir estado inicial de conectividade
INSERT OR IGNORE INTO system_state (key, value) 
VALUES ('connectivity_state', 'UNKNOWN');

-- ============================================
-- Tabela de eventos de métricas
-- ============================================
CREATE TABLE IF NOT EXISTS metrics_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metric_name TEXT NOT NULL,
    value REAL NOT NULL,
    labels TEXT,  -- JSON com labels adicionais
    device_id TEXT NOT NULL
);

-- Índices para métricas
CREATE INDEX IF NOT EXISTS idx_metrics_timestamp 
    ON metrics_events(timestamp);

CREATE INDEX IF NOT EXISTS idx_metrics_name 
    ON metrics_events(metric_name);

CREATE INDEX IF NOT EXISTS idx_metrics_device 
    ON metrics_events(device_id);

-- ============================================
-- Tabela de controle de migrations
-- ============================================
CREATE TABLE IF NOT EXISTS migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

-- Registrar esta migration
INSERT OR IGNORE INTO migrations (version, description) 
VALUES (1, 'Initial schema - queue_items, system_state, metrics_events');
