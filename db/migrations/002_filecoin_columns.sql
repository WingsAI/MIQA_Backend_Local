-- Migration 002: Filecoin/IPFS tracking columns
-- Adiciona colunas para rastreamento de publicação no IPFS/Filecoin

ALTER TABLE queue_items ADD COLUMN ipfs_status TEXT DEFAULT NULL;
-- NULL = não processado, PENDING = na fila, PUBLISHED = publicado, FAILED = falhou

ALTER TABLE queue_items ADD COLUMN ipfs_image_cid TEXT DEFAULT NULL;
-- CID da imagem original no IPFS

ALTER TABLE queue_items ADD COLUMN ipfs_manifest_cid TEXT DEFAULT NULL;
-- CID do manifest JSON (resultado MIQA linkado à imagem)

ALTER TABLE queue_items ADD COLUMN ipfs_published_at REAL DEFAULT NULL;
-- Timestamp Unix da publicação

-- Índice para o FilecoinWorker buscar itens pendentes eficientemente
CREATE INDEX IF NOT EXISTS idx_ipfs_status ON queue_items(ipfs_status);
