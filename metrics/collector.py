"""
Metrics Collector - Coleta e registra métricas do sistema
"""

import json
import logging
from datetime import datetime
from typing import Dict, Optional

from db.repository import QueueRepository

logger = logging.getLogger(__name__)

class MetricsCollector:
    """
    Coletor de métricas do sistema
    
    Registra métricas no SQLite para posterior análise ou exportação
    """
    
    def __init__(self, device_id: str, db_path: str = "./db/miqa.db"):
        self.device_id = device_id
        self.repository = QueueRepository(db_path)
        
        logger.info(f"MetricsCollector inicializado (device_id: {device_id})")
    
    def record_metric(self, name: str, value: float, labels: Optional[Dict] = None):
        """
        Registra métrica no SQLite
        
        Args:
            name: Nome da métrica (ex: 'items_detected_total')
            value: Valor numérico
            labels: Labels adicionais (dict)
        """
        import sqlite3
        
        conn = self.repository._get_conn()
        cursor = conn.cursor()
        
        try:
            # Adicionar device_id aos labels
            if labels is None:
                labels = {}
            labels['device_id'] = self.device_id
            
            # Inserir métrica
            cursor.execute("""
                INSERT INTO metrics_events (metric_name, value, labels, device_id)
                VALUES (?, ?, ?, ?)
            """, (name, value, json.dumps(labels), self.device_id))
            
            conn.commit()
            logger.debug(f"Métrica registrada: {name}={value} {labels}")
        
        except Exception as e:
            logger.error(f"Erro ao registrar métrica {name}: {e}")
            conn.rollback()
        
        finally:
            conn.close()
    
    def increment(self, name: str, labels: Optional[Dict] = None, amount: float = 1.0):
        """
        Incrementa contador
        
        Args:
            name: Nome do contador
            labels: Labels adicionais
            amount: Valor a incrementar (padrão: 1.0)
        """
        self.record_metric(name, amount, labels)
    
    def gauge(self, name: str, value: float, labels: Optional[Dict] = None):
        """
        Registra gauge (valor absoluto)
        
        Args:
            name: Nome do gauge
            value: Valor atual
            labels: Labels adicionais
        """
        self.record_metric(name, value, labels)
    
    def histogram(self, name: str, value: float, labels: Optional[Dict] = None):
        """
        Registra valor de histograma
        
        Args:
            name: Nome do histograma
            value: Valor observado
            labels: Labels adicionais
        """
        self.record_metric(name, value, labels)
    
    def get_metrics_summary(self, since_minutes: int = 60) -> Dict:
        """
        Retorna resumo de métricas
        
        Args:
            since_minutes: Últimos N minutos
        
        Returns:
            Dict com resumo
        """
        import sqlite3
        from datetime import timedelta
        
        conn = self.repository._get_conn()
        cursor = conn.cursor()
        
        since = (datetime.now() - timedelta(minutes=since_minutes)).isoformat()
        
        try:
            # Total de eventos
            cursor.execute("""
                SELECT COUNT(*) FROM metrics_events
                WHERE timestamp >= ?
            """, (since,))
            total_events = cursor.fetchone()[0]
            
            # Métricas por nome
            cursor.execute("""
                SELECT metric_name, COUNT(*), AVG(value), MIN(value), MAX(value)
                FROM metrics_events
                WHERE timestamp >= ?
                GROUP BY metric_name
            """, (since,))
            
            metrics_by_name = {}
            for row in cursor.fetchall():
                name, count, avg, min_val, max_val = row
                metrics_by_name[name] = {
                    'count': count,
                    'avg': round(avg, 2) if avg else 0,
                    'min': round(min_val, 2) if min_val else 0,
                    'max': round(max_val, 2) if max_val else 0
                }
            
            return {
                'total_events': total_events,
                'since_minutes': since_minutes,
                'metrics': metrics_by_name
            }
        
        finally:
            conn.close()


# Métricas padrão do sistema
class SystemMetrics:
    """Métricas padrão do sistema"""
    
    # Contadores
    ITEMS_DETECTED_TOTAL = "items_detected_total"
    ITEMS_UPLOADED_TOTAL = "items_uploaded_total"
    ITEMS_PROCESSED_LOCAL_TOTAL = "items_processed_local_total"
    UPLOAD_FAILURES_TOTAL = "upload_failures_total"
    PROCESSING_FAILURES_TOTAL = "processing_failures_total"
    
    # Gauges
    QUEUE_PENDING_CLOUD = "queue_pending_cloud"
    QUEUE_PENDING_LOCAL = "queue_pending_local"
    CONNECTIVITY_STATE = "connectivity_state"  # 1=ONLINE, 0=OFFLINE
    
    # Histogramas
    UPLOAD_DURATION_SECONDS = "upload_duration_seconds"
    PROCESSING_DURATION_SECONDS = "processing_duration_seconds"
    HEALTHCHECK_LATENCY_MS = "healthcheck_latency_ms"
    IMAGE_SIZE_BYTES = "image_size_bytes"
    QUALITY_SCORE = "quality_score"
