"""
Cloud Worker - Envia imagens para API de produção quando online
"""

import asyncio
import httpx
import logging
from pathlib import Path
from typing import Optional

from db.repository import QueueRepository

logger = logging.getLogger(__name__)

class CloudWorker:
    """
    Worker que envia imagens para API de produção
    
    Ativado quando:
    - Sistema está ONLINE ou DEGRADED
    - Há itens com cloud_status = PENDING ou FAILED
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.repository = QueueRepository(config['database']['path'])
        
        # Configurações
        self.api_url = config['cloud']['api_url']
        self.upload_timeout = config['cloud']['upload_timeout']
        self.max_retries = config['cloud']['max_retries']
        self.retry_backoff = config['cloud']['retry_backoff']
        
        self.worker_interval = config['workers']['cloud_worker_interval']
        self.max_concurrent = config['workers']['max_concurrent_uploads']
        
        self.device_id = config.get('device_id', 'unknown')
        
        logger.info("CloudWorker inicializado")
        logger.info(f"API URL: {self.api_url}")
        logger.info(f"Timeout: {self.upload_timeout}s")
        logger.info(f"Max concurrent: {self.max_concurrent}")
    
    async def run(self):
        """Loop principal de envio"""
        logger.info("☁️  Cloud Worker iniciado")

        # Aguardar connectivity_manager inicializar estado
        await asyncio.sleep(2)

        try:
            while True:
                # Verificar se deve enviar para cloud
                if not self._should_upload_to_cloud():
                    logger.debug("Sistema OFFLINE ou FORCED_OFFLINE, aguardando...")
                    await asyncio.sleep(self.worker_interval * 2)
                    continue
                
                # Processar itens pendentes
                items = self.repository.get_pending_cloud(limit=self.max_concurrent)
                
                if not items:
                    logger.debug("Nenhum item pendente para cloud")
                    await asyncio.sleep(self.worker_interval)
                    continue
                
                logger.info(f"📋 {len(items)} itens para enviar para cloud")
                
                # Processar em paralelo
                tasks = [self._upload_item(item) for item in items]
                await asyncio.gather(*tasks)
                
                # Aguardar antes de próxima verificação
                await asyncio.sleep(self.worker_interval)
        
        except KeyboardInterrupt:
            logger.info("Parando cloud worker...")
    
    def _should_upload_to_cloud(self) -> bool:
        """
        Verifica se deve enviar para cloud

        Returns:
            True se deve enviar
        """
        # Verificar modo forçado offline (config)
        if self.config.get('mode') == 'FORCED_OFFLINE':
            return False

        # Verificar estado de conectividade no banco
        state = self.repository.get_system_state('connectivity_state')

        # Nunca enviar se OFFLINE ou FORCED_OFFLINE
        if state in ('OFFLINE', 'FORCED_OFFLINE'):
            return False

        # Enviar se ONLINE ou DEGRADED
        if state in ('ONLINE', 'DEGRADED'):
            return True

        return False
    
    async def _upload_item(self, item: dict):
        """
        Envia item para cloud
        
        Args:
            item: Dict com dados do item
        """
        item_uid = item['item_uid']
        path = Path(item['path'])
        
        logger.info(f"☁️  Enviando para cloud: {item_uid[:16]}... ({path.name})")
        
        # Claim do item (lock)
        try:
            self.repository.mark_cloud_uploading(item_uid, lock_duration_minutes=5)
        except Exception as e:
            logger.error(f"❌ Erro ao fazer claim de {item_uid}: {e}")
            return
        
        # Tentar upload com retry
        for attempt in range(1, self.max_retries + 1):
            try:
                success = await self._try_upload(item_uid, path, item, attempt)
                
                if success:
                    return  # Sucesso, sair
                
                # Se falhou mas ainda tem tentativas, aguardar com backoff
                if attempt < self.max_retries:
                    wait_time = self.retry_backoff ** attempt
                    logger.warning(f"⏳ Retry {attempt}/{self.max_retries} em {wait_time}s...")
                    await asyncio.sleep(wait_time)
            
            except Exception as e:
                logger.error(f"❌ Erro inesperado no upload (tentativa {attempt}): {e}")
                
                if attempt >= self.max_retries:
                    # Esgotou tentativas
                    error = f"Falhou após {self.max_retries} tentativas: {e}"
                    self.repository.mark_cloud_failed(
                        item_uid, 
                        error,
                        retry_delay_minutes=30  # Retry em 30min
                    )
                    return
    
    async def _try_upload(self, item_uid: str, path: Path, item: dict, attempt: int) -> bool:
        """
        Tenta fazer upload
        
        Args:
            item_uid: UID do item
            path: Caminho do arquivo
            item: Dict com metadados
            attempt: Número da tentativa
        
        Returns:
            True se sucesso, False se falha
        """
        # Verificar se arquivo existe
        if not path.exists():
            error = f"Arquivo não encontrado: {path}"
            logger.error(f"❌ {error}")
            self.repository.mark_cloud_failed(item_uid, error)
            return True  # Não retry (arquivo não existe)
        
        try:
            async with httpx.AsyncClient() as client:
                # Ler arquivo completamente antes de enviar
                with open(path, 'rb') as f:
                    file_content = f.read()
                
                # Preparar arquivo para upload
                files = {'file': (path.name, file_content, 'image/jpeg')}
                
                # Preparar dados
                data = {
                    'modality': item.get('meta_modality') or 'mri',
                    'device_id': self.device_id
                }
                
                # Headers com idempotência
                headers = {
                    'Idempotency-Key': item_uid
                }
                
                # Fazer POST
                endpoint = f"{self.api_url}/api/v1/miqa/analyze"
                
                logger.debug(f"POST {endpoint} (tentativa {attempt})")
                
                response = await client.post(
                    endpoint,
                    files=files,
                    data=data,
                    headers=headers,
                    timeout=self.upload_timeout
                )
                
                
                # Verificar resposta
                if response.status_code == 200:
                    # Salvar resultado da nuvem localmente
                    try:
                        result_data = response.json()
                        self._save_cloud_result(item_uid, result_data, path)
                    except Exception as e:
                        logger.warning(f"Não foi possível salvar resultado da nuvem: {e}")
                    
                    # Marcar cloud como uploaded
                    self.repository.mark_cloud_uploaded(item_uid)
                    
                    # Marcar local como DONE também (não precisa processar localmente)
                    import sqlite3
                    conn = self.repository._get_conn()
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE queue_items 
                        SET local_status = 'DONE'
                        WHERE item_uid = ?
                    """, (item_uid,))
                    conn.commit()
                    conn.close()
                    
                    logger.info(f"✅ Upload OK: {item_uid[:16]}... (HTTP 200)")
                    return True
                
                elif response.status_code == 409:
                    # Conflito - já foi processado (idempotência)
                    logger.info(f"✅ Upload OK (duplicado): {item_uid[:16]}... (HTTP 409)")
                    self.repository.mark_cloud_uploaded(item_uid)
                    return True
                
                elif response.status_code in (400, 422):
                    # Erro de validação - não retry
                    error = f"Validação falhou: HTTP {response.status_code} - {response.text[:200]}"
                    logger.error(f"❌ {error}")
                    self.repository.mark_cloud_failed(item_uid, error)
                    return True  # Não retry
                
                elif response.status_code >= 500:
                    # Erro do servidor - retry
                    error = f"Erro do servidor: HTTP {response.status_code}"
                    logger.warning(f"⚠️  {error} (tentativa {attempt})")
                    return False  # Retry
                
                else:
                    # Outro erro
                    error = f"HTTP {response.status_code}: {response.text[:200]}"
                    logger.warning(f"⚠️  {error} (tentativa {attempt})")
                    return False  # Retry
        
        except httpx.TimeoutException:
            error = f"Timeout após {self.upload_timeout}s"
            logger.warning(f"⚠️  {error} (tentativa {attempt})")
            return False  # Retry
        
        except httpx.ConnectError as e:
            error = f"Erro de conexão: {e}"
            logger.warning(f"⚠️  {error} (tentativa {attempt})")
            return False  # Retry
        
        except Exception as e:
            error = f"Erro inesperado: {e}"
            logger.error(f"❌ {error}")
            raise  # Re-raise para ser tratado no caller
    
    def _save_cloud_result(self, item_uid: str, result_data: dict, image_path: Path):
        """
        Salva resultado da nuvem localmente
        
        Args:
            item_uid: UID do item
            result_data: Resposta da API
            image_path: Caminho da imagem original
        """
        import json
        import time
        
        # Criar diretório results/online
        results_dir = Path("./results/online")
        results_dir.mkdir(parents=True, exist_ok=True)
        
        # Adicionar metadados
        result_data['item_uid'] = item_uid
        result_data['image_path'] = str(image_path)
        result_data['processed_at'] = time.time()
        result_data['processed_by'] = 'cloud_worker'
        result_data['device_id'] = self.device_id
        
        # Salvar JSON
        filename = f"{item_uid}.json"
        filepath = results_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 Resultado da nuvem salvo: {filepath}")
    
    def get_stats(self) -> dict:
        """
        Retorna estatísticas do worker
        
        Returns:
            Dict com estatísticas
        """
        import sqlite3
        
        conn = self.repository._get_conn()
        cursor = conn.cursor()
        
        # Total enviado
        cursor.execute("""
            SELECT COUNT(*) FROM queue_items 
            WHERE cloud_status = 'UPLOADED'
        """)
        total_uploaded = cursor.fetchone()[0]
        
        # Total falhado
        cursor.execute("""
            SELECT COUNT(*) FROM queue_items 
            WHERE cloud_status = 'FAILED'
        """)
        total_failed = cursor.fetchone()[0]
        
        # Pendentes
        cursor.execute("""
            SELECT COUNT(*) FROM queue_items 
            WHERE cloud_status IN ('PENDING', 'UPLOADING')
        """)
        total_pending = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_uploaded': total_uploaded,
            'total_failed': total_failed,
            'total_pending': total_pending,
            'api_url': self.api_url,
            'should_upload': self._should_upload_to_cloud()
        }
