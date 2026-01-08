"""
Metrics Exporter - Exporta métricas para arquivo ou console
"""

import json
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import Dict

from metrics.collector import MetricsCollector

logger = logging.getLogger(__name__)

class MetricsExporter:
    """
    Exportador de métricas
    
    Exporta métricas acumuladas para arquivo JSON ou console
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.device_id = config.get('device_id', 'unknown')
        self.collector = MetricsCollector(
            device_id=self.device_id,
            db_path=config['database']['path']
        )
        
        self.export_interval = config.get('metrics', {}).get('export_interval', 60)
        self.export_dir = Path(config.get('metrics', {}).get('export_dir', './metrics_export'))
        self.export_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("MetricsExporter inicializado")
        logger.info(f"Export interval: {self.export_interval}s")
        logger.info(f"Export dir: {self.export_dir}")
    
    def run(self):
        """Loop principal de exportação"""
        logger.info("📊 Metrics Exporter iniciado")
        
        try:
            while True:
                self._export_metrics()
                time.sleep(self.export_interval)
        
        except KeyboardInterrupt:
            logger.info("Parando metrics exporter...")
    
    def _export_metrics(self):
        """Exporta métricas"""
        try:
            # Obter resumo
            summary = self.collector.get_metrics_summary(since_minutes=60)
            
            # Adicionar timestamp
            export_data = {
                'timestamp': datetime.now().isoformat(),
                'device_id': self.device_id,
                'summary': summary
            }
            
            # Exportar para arquivo
            filename = f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = self.export_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✅ Métricas exportadas: {filepath}")
            
            # Log resumo
            logger.info(f"Total de eventos: {summary['total_events']}")
            for metric_name, stats in summary['metrics'].items():
                logger.info(f"  {metric_name}: count={stats['count']}, avg={stats['avg']}")
        
        except Exception as e:
            logger.error(f"❌ Erro ao exportar métricas: {e}", exc_info=True)
    
    def export_now(self) -> Dict:
        """
        Exporta métricas imediatamente
        
        Returns:
            Dict com dados exportados
        """
        summary = self.collector.get_metrics_summary(since_minutes=60)
        
        export_data = {
            'timestamp': datetime.now().isoformat(),
            'device_id': self.device_id,
            'summary': summary
        }
        
        return export_data
