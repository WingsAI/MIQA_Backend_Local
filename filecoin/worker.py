"""
Filecoin Worker — Publica imagens médicas e resultados MIQA no IPFS/Filecoin

Roda como worker assíncrono paralelo ao CloudWorker e LocalWorker.
Não bloqueia o pipeline principal — o upload IPFS é best-effort.

Fluxo:
    Resultado gerado (online ou offline)
    → FilecoinWorker detecta itens com ipfs_status = PENDING
    → Upload da imagem original → CID da imagem
    → Upload do manifest JSON (resultado + CID imagem) → CID do manifest
    → Grava CIDs no SQLite para rastreabilidade
    → Salva registro em ./results/ipfs/
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

from db.repository import QueueRepository
from filecoin.ipfs_client import IPFSClient, IPFSResult

logger = logging.getLogger(__name__)

RESULTS_IPFS_DIR = Path("./results/ipfs")


class FilecoinWorker:
    """
    Worker que publica dados MIQA no Filecoin via IPFS.

    Publicar no IPFS não é obrigatório para o sistema funcionar —
    é uma camada adicional de transparência e soberania de dados.
    Falhas no upload IPFS são logadas mas não interrompem o pipeline.
    """

    def __init__(self, config: dict):
        self.config = config
        self.repository = QueueRepository(config["database"]["path"])

        filecoin_cfg = config.get("filecoin", {})
        self.enabled = filecoin_cfg.get("enabled", False)
        self.api_key = filecoin_cfg.get("api_key")
        self.backend = filecoin_cfg.get("backend", "lighthouse")
        self.worker_interval = filecoin_cfg.get("worker_interval", 30)
        self.upload_images = filecoin_cfg.get("upload_images", True)

        if self.enabled:
            self.client = IPFSClient(api_key=self.api_key, backend=self.backend)
            RESULTS_IPFS_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"FilecoinWorker iniciado — backend: {self.backend}")
        else:
            self.client = None
            logger.info("FilecoinWorker desabilitado (filecoin.enabled=false no config)")

    async def run(self):
        """Loop principal do worker"""
        if not self.enabled:
            logger.info("FilecoinWorker inativo — saindo")
            return

        logger.info("FilecoinWorker iniciado")
        await asyncio.sleep(5)  # Aguarda outros workers inicializarem

        while True:
            try:
                await self._process_pending()
            except Exception as e:
                logger.error(f"Erro no FilecoinWorker: {e}")

            await asyncio.sleep(self.worker_interval)

    async def _process_pending(self):
        """Processa itens com resultado pronto mas ainda não publicados no IPFS"""
        items = self._get_items_ready_for_ipfs()

        if not items:
            logger.debug("Nenhum item pendente para IPFS")
            return

        logger.info(f"FilecoinWorker: {len(items)} itens para publicar no IPFS")

        for item in items:
            await self._publish_item(item)

    def _get_items_ready_for_ipfs(self) -> list[dict]:
        """
        Busca itens que já têm resultado (local ou cloud) mas não foram publicados no IPFS.

        Usa uma coluna ipfs_status na tabela queue_items (adicionada via migração).
        Fallback seguro: se a coluna não existir, busca por itens DONE sem ipfs_cid.
        """
        import sqlite3

        conn = self.repository._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT item_uid, path, meta_modality, result_path, cloud_status, local_status
                FROM queue_items
                WHERE (cloud_status = 'UPLOADED' OR local_status = 'DONE')
                  AND (ipfs_status IS NULL OR ipfs_status = 'PENDING')
                LIMIT 5
            """)
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in rows]
        except sqlite3.OperationalError:
            # Coluna ipfs_status ainda não existe — migração pendente
            logger.debug("Coluna ipfs_status não encontrada — migração pendente")
            return []
        finally:
            conn.close()

    async def _publish_item(self, item: dict):
        """
        Publica imagem e resultado de um item no IPFS/Filecoin.

        Args:
            item: Dict com dados do item da fila
        """
        item_uid = item["item_uid"]
        image_path = Path(item["path"])
        modality = item.get("meta_modality", "unknown")
        result_path = item.get("result_path")

        logger.info(f"Publicando no IPFS: {item_uid[:16]}...")

        image_cid: Optional[str] = None
        manifest_cid: Optional[str] = None

        # 1. Upload da imagem original (opcional — pode ser desabilitado por privacidade)
        if self.upload_images and image_path.exists():
            img_result = await self.client.upload_image(
                image_path, item_uid, modality=modality
            )
            if img_result.success:
                image_cid = img_result.cid
                logger.info(f"Imagem publicada: {image_cid}")
            else:
                logger.warning(f"Falha upload imagem IPFS: {img_result.error}")

        # 2. Upload do manifest de resultado
        result_data = self._load_result(result_path, item_uid)
        if result_data:
            manifest_result = await self.client.upload_result_manifest(
                result_data, item_uid, image_cid=image_cid
            )
            if manifest_result.success:
                manifest_cid = manifest_result.cid
                logger.info(f"Manifest publicado: {manifest_cid}")
            else:
                logger.warning(f"Falha upload manifest IPFS: {manifest_result.error}")

        # 3. Gravar CIDs no banco e salvar registro local
        self._save_ipfs_record(item_uid, image_cid, manifest_cid, result_data)

    def _load_result(self, result_path: Optional[str], item_uid: str) -> Optional[dict]:
        """Carrega resultado JSON do item (online ou offline)"""
        if result_path and Path(result_path).exists():
            try:
                with open(result_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Erro ao ler resultado {result_path}: {e}")

        # Tentar localizar nos diretórios padrão
        for base in [Path("./results/online"), Path("./results/offline")]:
            candidate = base / f"{item_uid}.json"
            if candidate.exists():
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

        logger.warning(f"Resultado não encontrado para {item_uid[:16]}")
        return None

    def _save_ipfs_record(
        self,
        item_uid: str,
        image_cid: Optional[str],
        manifest_cid: Optional[str],
        result_data: Optional[dict],
    ):
        """Grava CIDs no SQLite e salva registro local em ./results/ipfs/"""
        import sqlite3

        # Atualizar banco
        conn = self.repository._get_conn()
        cursor = conn.cursor()
        try:
            status = "PUBLISHED" if (image_cid or manifest_cid) else "FAILED"
            cursor.execute("""
                UPDATE queue_items
                SET ipfs_status = ?,
                    ipfs_image_cid = ?,
                    ipfs_manifest_cid = ?,
                    ipfs_published_at = ?
                WHERE item_uid = ?
            """, (status, image_cid, manifest_cid, time.time(), item_uid))
            conn.commit()
        except sqlite3.OperationalError as e:
            logger.warning(f"Não foi possível gravar CIDs no banco: {e}")
        finally:
            conn.close()

        # Salvar registro local
        record = {
            "item_uid": item_uid,
            "image_cid": image_cid,
            "manifest_cid": manifest_cid,
            "image_gateway": f"https://gateway.lighthouse.storage/ipfs/{image_cid}" if image_cid else None,
            "manifest_gateway": f"https://gateway.lighthouse.storage/ipfs/{manifest_cid}" if manifest_cid else None,
            "published_at": time.time(),
            "miqa_result": result_data,
        }

        record_path = RESULTS_IPFS_DIR / f"{item_uid}.json"
        try:
            with open(record_path, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2, ensure_ascii=False)
            logger.info(f"Registro IPFS salvo: {record_path}")
        except Exception as e:
            logger.error(f"Erro ao salvar registro IPFS: {e}")

    def get_stats(self) -> dict:
        """Retorna estatísticas do worker"""
        if not self.enabled:
            return {"enabled": False}

        import sqlite3

        conn = self.repository._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT COUNT(*) FROM queue_items WHERE ipfs_status = 'PUBLISHED'")
            published = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM queue_items WHERE ipfs_status = 'FAILED'")
            failed = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COUNT(*) FROM queue_items WHERE ipfs_status IS NULL OR ipfs_status = 'PENDING'"
            )
            pending = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            published = failed = pending = 0
        finally:
            conn.close()

        return {
            "enabled": True,
            "backend": self.backend,
            "published": published,
            "failed": failed,
            "pending": pending,
        }
