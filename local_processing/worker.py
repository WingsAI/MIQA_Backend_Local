"""
Local Worker - Processa imagens localmente quando offline
"""

import logging
import json
import time
from pathlib import Path
import cv2
import numpy as np

from db.repository import QueueRepository
from local_processing.miqa_core import MIQAAnalyzer

logger = logging.getLogger(__name__)

class LocalWorker:
    """
    Worker que processa imagens localmente
    
    Ativado quando:
    - Sistema está OFFLINE
    - Sistema está em modo FORCED_OFFLINE
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.repository = QueueRepository(config['database']['path'])
        
        # Inicializar analisador MIQA
        try:
            self.analyzer = MIQAAnalyzer()
            logger.info("✅ MIQAAnalyzer inicializado")
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar MIQAAnalyzer: {e}")
            raise
        
        # Configurações
        self.results_dir = Path(config['directories']['results'])
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        self.worker_interval = config['workers']['local_worker_interval']
        self.max_concurrent = config['workers']['max_concurrent_processing']
        
        logger.info("LocalWorker inicializado")
        logger.info(f"Resultados: {self.results_dir}")
        logger.info(f"Intervalo: {self.worker_interval}s")
        logger.info(f"Max concurrent: {self.max_concurrent}")
    
    def run(self):
        """Loop principal de processamento"""
        logger.info("💻 Local Worker iniciado")
        
        try:
            while True:
                # Verificar se deve processar localmente
                if not self._should_process_locally():
                    logger.debug("Sistema ONLINE, aguardando...")
                    time.sleep(self.worker_interval * 2)  # Aguardar mais tempo
                    continue
                
                # Processar itens pendentes
                items = self.repository.get_pending_local(limit=self.max_concurrent)
                
                if not items:
                    logger.debug("Nenhum item pendente para processamento local")
                    time.sleep(self.worker_interval)
                    continue
                
                logger.info(f"📋 {len(items)} itens para processar localmente")
                
                # Processar cada item
                for item in items:
                    self._process_item(item)
                
                # Aguardar antes de próxima verificação
                time.sleep(self.worker_interval)
        
        except KeyboardInterrupt:
            logger.info("Parando local worker...")
    
    def _should_process_locally(self) -> bool:
        """
        Verifica se deve processar localmente
        
        Returns:
            True se deve processar localmente
        """
        # Verificar modo forçado offline
        if self.config.get('mode') == 'FORCED_OFFLINE':
            return True
        
        # Verificar estado de conectividade
        state = self.repository.get_system_state('connectivity_state')
        
        if state in ('OFFLINE', 'FORCED_OFFLINE'):
            return True
        
        return False
    
    def _process_item(self, item: dict):
        """
        Processa item localmente
        
        Args:
            item: Dict com dados do item
        """
        item_uid = item['item_uid']
        path = Path(item['path'])
        
        logger.info(f"🔬 Processando localmente: {item_uid[:16]}... ({path.name})")
        
        # Claim do item (lock)
        try:
            self.repository.mark_local_processing(item_uid, lock_duration_minutes=10)
        except Exception as e:
            logger.error(f"❌ Erro ao fazer claim de {item_uid}: {e}")
            return
        
        # Processar
        start_time = time.time()
        
        try:
            # Carregar imagem
            if not path.exists():
                raise FileNotFoundError(f"Arquivo não encontrado: {path}")
            
            image = cv2.imread(str(path))
            
            if image is None:
                raise ValueError(f"Não foi possível carregar imagem: {path}")
            
            # Converter para RGB (OpenCV usa BGR)
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # Processar com MIQA
            modality = item.get('meta_modality') or 'mri'
            
            logger.debug(f"Analisando com modalidade: {modality}")
            result = self.analyzer.analyze(image_rgb, modality=modality)
            
            # Adicionar metadados
            result['item_uid'] = item_uid
            result['path'] = str(path)
            result['modality'] = modality
            result['processed_at'] = time.time()
            result['processing_time_seconds'] = time.time() - start_time
            result['processed_by'] = 'local_worker'
            result['device_id'] = self.config.get('device_id', 'unknown')
            
            # Salvar resultado
            result_path = self._save_result(item_uid, result)
            
            # Marcar como concluído
            self.repository.mark_local_done(item_uid, str(result_path))
            
            duration = time.time() - start_time
            logger.info(f"✅ Processamento local OK: {item_uid[:16]}... ({duration:.2f}s, score: {result.get('score', 'N/A')})")
            
            # Política de reconciliação: marcar para enviar para nuvem quando voltar online
            # Isso será implementado no cloud_worker
            
        except FileNotFoundError as e:
            error = f"Arquivo não encontrado: {e}"
            logger.error(f"❌ {error}")
            self.repository.mark_local_failed(item_uid, error)
        
        except ValueError as e:
            error = f"Erro ao carregar imagem: {e}"
            logger.error(f"❌ {error}")
            self.repository.mark_local_failed(item_uid, error)
        
        except Exception as e:
            error = f"Erro no processamento: {e}"
            logger.error(f"❌ Erro ao processar {item_uid}: {e}", exc_info=True)
            self.repository.mark_local_failed(item_uid, error)
    
    def _save_result(self, item_uid: str, result: dict) -> Path:
        """
        Salva resultado em arquivo JSON
        
        Args:
            item_uid: UID do item
            result: Resultado do processamento
        
        Returns:
            Path do arquivo salvo
        """
        # Nome do arquivo
        filename = f"{item_uid}.json"
        filepath = self.results_dir / filename
        
        # Salvar JSON
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        logger.debug(f"Resultado salvo: {filepath}")
        
        return filepath
    
    def get_stats(self) -> dict:
        """
        Retorna estatísticas do worker
        
        Returns:
            Dict com estatísticas
        """
        import sqlite3
        
        conn = self.repository._get_conn()
        cursor = conn.cursor()
        
        # Total processado localmente
        cursor.execute("""
            SELECT COUNT(*) FROM queue_items 
            WHERE local_status = 'DONE'
        """)
        total_processed = cursor.fetchone()[0]
        
        # Total falhado
        cursor.execute("""
            SELECT COUNT(*) FROM queue_items 
            WHERE local_status = 'FAILED'
        """)
        total_failed = cursor.fetchone()[0]
        
        # Pendentes
        cursor.execute("""
            SELECT COUNT(*) FROM queue_items 
            WHERE local_status = 'PENDING'
        """)
        total_pending = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_processed': total_processed,
            'total_failed': total_failed,
            'total_pending': total_pending,
            'results_dir': str(self.results_dir),
            'should_process': self._should_process_locally()
        }
