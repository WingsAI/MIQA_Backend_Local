"""
Sync Worker - Sincroniza resultados offline com API de produção
"""

import json
import logging
import time
from pathlib import Path

import httpx

from db.repository import QueueRepository

logger = logging.getLogger(__name__)


class SyncWorker:
    """
    Worker que sincroniza resultados offline com API de produção.

    Quando internet volta (ONLINE):
    1. Lê JSONs de results/offline/
    2. Envia para API de produção
    3. Deleta arquivo após sincronizar
    """

    def __init__(self, config: dict):
        self.config = config
        self.repository = QueueRepository(config['database']['path'])

        # Diretórios
        self.offline_dir = Path("./results/offline")

        # API config
        self.api_url = config['cloud']['api_url']
        self.sync_endpoint = config.get('sync', {}).get(
            'endpoint',
            '/api/v1/miqa/sync-offline'
        )
        self.device_id = config.get('device_id', 'unknown')

        # Configurações
        self.sync_interval = config.get('sync', {}).get('interval', 30)
        self.delete_after_sync = config.get('sync', {}).get('delete_after_sync', True)
        self.timeout = config.get('sync', {}).get('timeout', 30)

        logger.info("SyncWorker inicializado")
        logger.info(f"API: {self.api_url}{self.sync_endpoint}")
        logger.info(f"Intervalo: {self.sync_interval}s")

    def run(self):
        """Loop principal de sincronização"""
        logger.info("🔄 Sync Worker iniciado")

        try:
            while True:
                # Só sincroniza quando ONLINE
                if self._is_online():
                    self._sync_offline_results()
                else:
                    logger.debug("Sistema OFFLINE, aguardando para sincronizar...")

                time.sleep(self.sync_interval)

        except KeyboardInterrupt:
            logger.info("Parando sync worker...")

    def _is_online(self) -> bool:
        """Verifica se está online"""
        state = self.repository.get_system_state('connectivity_state')
        return state in ('ONLINE', 'DEGRADED')

    def _sync_offline_results(self):
        """Sincroniza resultados offline"""
        if not self.offline_dir.exists():
            return

        json_files = list(self.offline_dir.glob("*.json"))

        if not json_files:
            logger.debug("Nenhum resultado offline para sincronizar")
            return

        logger.info(f"📤 {len(json_files)} resultados offline para sincronizar")

        synced = 0
        failed = 0

        for json_file in json_files:
            try:
                success = self._sync_to_api(json_file)

                if success:
                    if self.delete_after_sync:
                        json_file.unlink()
                    synced += 1
                    logger.info(f"✅ Sincronizado: {json_file.name}")
                else:
                    failed += 1
                    logger.warning(f"⚠️ Falha: {json_file.name}")

            except Exception as e:
                failed += 1
                logger.error(f"❌ Erro ao sincronizar {json_file.name}: {e}")

        if synced > 0 or failed > 0:
            logger.info(f"📊 Sync completo: {synced} OK, {failed} falhas")

    def _sync_to_api(self, json_file: Path) -> bool:
        """
        Envia resultado para API de produção

        Args:
            json_file: Arquivo JSON com resultado

        Returns:
            True se enviou com sucesso
        """
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)

            # Adicionar metadados de sync
            payload = {
                'device_id': self.device_id,
                'item_uid': data.get('item_uid'),
                'result': data,
                'synced_at': time.time(),
                'source': 'offline_sync'
            }

            url = f"{self.api_url}{self.sync_endpoint}"

            response = httpx.post(
                url,
                json=payload,
                headers={
                    'Content-Type': 'application/json',
                    'X-Device-ID': self.device_id,
                    'X-Sync-Source': 'offline'
                },
                timeout=self.timeout
            )

            if response.status_code in (200, 201, 202):
                return True
            else:
                logger.error(f"API retornou {response.status_code}: {response.text[:200]}")
                return False

        except httpx.RequestError as e:
            logger.error(f"Erro de conexão: {e}")
            return False
        except Exception as e:
            logger.error(f"Erro ao processar {json_file}: {e}")
            return False

    def get_pending_count(self) -> int:
        """Retorna quantidade de arquivos pendentes"""
        if not self.offline_dir.exists():
            return 0
        return len(list(self.offline_dir.glob("*.json")))

    def sync_now(self) -> dict:
        """
        Força sincronização imediata

        Returns:
            Dict com resultado
        """
        if not self.offline_dir.exists():
            return {'synced': 0, 'failed': 0, 'pending': 0}

        json_files = list(self.offline_dir.glob("*.json"))
        synced = 0
        failed = 0

        for json_file in json_files:
            try:
                if self._sync_to_api(json_file):
                    if self.delete_after_sync:
                        json_file.unlink()
                    synced += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

        return {
            'synced': synced,
            'failed': failed,
            'pending': self.get_pending_count()
        }
