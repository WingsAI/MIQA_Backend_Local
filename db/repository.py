"""
Repository para acesso ao banco de dados SQLite
Implementa todas as operações de CRUD e controle de fila
"""

import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)

class QueueRepository:
    """Repository para gerenciar fila de processamento"""
    
    def __init__(self, db_path="./db/miqa.db"):
        self.db_path = db_path
    
    def _get_conn(self):
        """Cria conexão com banco de dados"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Retornar dicts
        return conn
    
    # ============================================
    # CRUD Básico
    # ============================================
    
    def upsert_item(self, item_uid: str, path: str, source_type: str, meta: Dict):
        """
        Insere ou atualiza item na fila
        
        Args:
            item_uid: Identificador único do item
            path: Caminho do arquivo
            source_type: 'LISTENER' ou 'DICOM'
            meta: Metadados (modality, device, exam_type)
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO queue_items (
                    item_uid, path, source_type, 
                    meta_modality, meta_device, meta_exam_type,
                    detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(item_uid) DO UPDATE SET
                    path = excluded.path,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                item_uid, 
                path, 
                source_type,
                meta.get('modality'), 
                meta.get('device'), 
                meta.get('exam_type')
            ))
            
            conn.commit()
            logger.debug(f"Item upserted: {item_uid}")
            
        except sqlite3.Error as e:
            logger.error(f"Erro ao upsert item {item_uid}: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    # ============================================
    # Seleção de Itens Pendentes
    # ============================================
    
    def get_pending_cloud(self, limit=10) -> List[Dict]:
        """
        Retorna itens pendentes para envio à nuvem
        
        Args:
            limit: Número máximo de itens
        
        Returns:
            Lista de dicts com dados dos itens
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        try:
            cursor.execute("""
                SELECT * FROM queue_items
                WHERE cloud_status IN ('PENDING', 'FAILED')
                AND (next_retry_at IS NULL OR next_retry_at <= ?)
                AND locked_until < ?
                ORDER BY detected_at ASC
                LIMIT ?
            """, (now, now, limit))
            
            items = [dict(row) for row in cursor.fetchall()]
            logger.debug(f"Encontrados {len(items)} itens pendentes para cloud")
            return items
            
        finally:
            conn.close()
    
    def get_pending_local(self, limit=10) -> List[Dict]:
        """
        Retorna itens pendentes para processamento local
        
        Args:
            limit: Número máximo de itens
        
        Returns:
            Lista de dicts com dados dos itens
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        try:
            cursor.execute("""
                SELECT * FROM queue_items
                WHERE local_status = 'PENDING'
                AND locked_until < ?
                ORDER BY detected_at ASC
                LIMIT ?
            """, (now, limit))
            
            items = [dict(row) for row in cursor.fetchall()]
            logger.debug(f"Encontrados {len(items)} itens pendentes para local")
            return items
            
        finally:
            conn.close()
    
    # ============================================
    # Atualização de Status - Cloud
    # ============================================
    
    def mark_cloud_uploading(self, item_uid: str, lock_duration_minutes=5):
        """
        Marca item como sendo enviado para nuvem (claim/lock)
        
        Args:
            item_uid: ID do item
            lock_duration_minutes: Duração do lock em minutos
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        locked_until = (datetime.now() + timedelta(minutes=lock_duration_minutes)).isoformat()
        
        try:
            cursor.execute("""
                UPDATE queue_items
                SET cloud_status = 'UPLOADING',
                    locked_until = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE item_uid = ?
            """, (locked_until, item_uid))
            
            conn.commit()
            logger.debug(f"Item {item_uid} marcado como UPLOADING")
            
        except sqlite3.Error as e:
            logger.error(f"Erro ao marcar {item_uid} como uploading: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def mark_cloud_uploaded(self, item_uid: str):
        """
        Marca item como enviado com sucesso
        
        Args:
            item_uid: ID do item
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE queue_items
                SET cloud_status = 'UPLOADED',
                    retry_count = 0,
                    last_error = NULL,
                    next_retry_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE item_uid = ?
            """, (item_uid,))
            
            conn.commit()
            logger.info(f"✅ Item {item_uid} enviado para cloud com sucesso")
            
        except sqlite3.Error as e:
            logger.error(f"Erro ao marcar {item_uid} como uploaded: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def mark_cloud_failed(self, item_uid: str, error: str, retry_delay_minutes=5):
        """
        Marca item como falha no envio
        
        Args:
            item_uid: ID do item
            error: Mensagem de erro
            retry_delay_minutes: Minutos até próxima tentativa
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        next_retry = (datetime.now() + timedelta(minutes=retry_delay_minutes)).isoformat()
        
        try:
            cursor.execute("""
                UPDATE queue_items
                SET cloud_status = 'FAILED',
                    retry_count = retry_count + 1,
                    last_error = ?,
                    next_retry_at = ?,
                    locked_until = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE item_uid = ?
            """, (error, next_retry, item_uid))
            
            conn.commit()
            logger.warning(f"❌ Item {item_uid} falhou no cloud: {error}")
            
        except sqlite3.Error as e:
            logger.error(f"Erro ao marcar {item_uid} como failed: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    # ============================================
    # Atualização de Status - Local
    # ============================================
    
    def mark_local_processing(self, item_uid: str, lock_duration_minutes=10):
        """
        Marca item como sendo processado localmente (claim/lock)
        
        Args:
            item_uid: ID do item
            lock_duration_minutes: Duração do lock em minutos
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        locked_until = (datetime.now() + timedelta(minutes=lock_duration_minutes)).isoformat()
        
        try:
            cursor.execute("""
                UPDATE queue_items
                SET local_status = 'PROCESSING',
                    locked_until = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE item_uid = ?
            """, (locked_until, item_uid))
            
            conn.commit()
            logger.debug(f"Item {item_uid} marcado como PROCESSING (local)")
            
        except sqlite3.Error as e:
            logger.error(f"Erro ao marcar {item_uid} como processing: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def mark_local_done(self, item_uid: str, result_path: str):
        """
        Marca item como processado localmente com sucesso
        
        Args:
            item_uid: ID do item
            result_path: Caminho do arquivo de resultado
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE queue_items
                SET local_status = 'DONE',
                    local_result_path = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE item_uid = ?
            """, (result_path, item_uid))
            
            conn.commit()
            logger.info(f"✅ Item {item_uid} processado localmente com sucesso")
            
        except sqlite3.Error as e:
            logger.error(f"Erro ao marcar {item_uid} como done: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def mark_local_failed(self, item_uid: str, error: str):
        """
        Marca item como falha no processamento local
        
        Args:
            item_uid: ID do item
            error: Mensagem de erro
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE queue_items
                SET local_status = 'FAILED',
                    last_error = ?,
                    locked_until = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE item_uid = ?
            """, (error, item_uid))
            
            conn.commit()
            logger.warning(f"❌ Item {item_uid} falhou no processamento local: {error}")
            
        except sqlite3.Error as e:
            logger.error(f"Erro ao marcar {item_uid} como failed (local): {e}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    # ============================================
    # Estado do Sistema
    # ============================================
    
    def get_system_state(self, key: str) -> Optional[str]:
        """
        Retorna valor do estado do sistema
        
        Args:
            key: Chave do estado
        
        Returns:
            Valor ou None
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT value FROM system_state WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row['value'] if row else None
        finally:
            conn.close()
    
    def set_system_state(self, key: str, value: str):
        """
        Define valor do estado do sistema
        
        Args:
            key: Chave do estado
            value: Valor
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO system_state (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
            """, (key, value))
            
            conn.commit()
            logger.debug(f"Estado do sistema atualizado: {key} = {value}")
            
        except sqlite3.Error as e:
            logger.error(f"Erro ao atualizar estado {key}: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    # ============================================
    # Estatísticas
    # ============================================
    
    def get_queue_stats(self) -> Dict:
        """
        Retorna estatísticas da fila
        
        Returns:
            Dict com estatísticas
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        try:
            # Total de itens
            cursor.execute("SELECT COUNT(*) as total FROM queue_items")
            total = cursor.fetchone()['total']
            
            # Pendentes cloud
            cursor.execute("""
                SELECT COUNT(*) as count FROM queue_items 
                WHERE cloud_status IN ('PENDING', 'FAILED')
            """)
            pending_cloud = cursor.fetchone()['count']
            
            # Pendentes local
            cursor.execute("""
                SELECT COUNT(*) as count FROM queue_items 
                WHERE local_status = 'PENDING'
            """)
            pending_local = cursor.fetchone()['count']
            
            # Completados
            cursor.execute("""
                SELECT COUNT(*) as count FROM queue_items 
                WHERE cloud_status = 'UPLOADED' OR local_status = 'DONE'
            """)
            completed = cursor.fetchone()['count']
            
            # Falhas
            cursor.execute("""
                SELECT COUNT(*) as count FROM queue_items 
                WHERE cloud_status = 'FAILED' OR local_status = 'FAILED'
            """)
            failed = cursor.fetchone()['count']
            
            return {
                'total': total,
                'pending_cloud': pending_cloud,
                'pending_local': pending_local,
                'completed': completed,
                'failed': failed
            }
        finally:
            conn.close()
