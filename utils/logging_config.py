"""
Configuração de logging estruturado em JSON
"""

import logging
import json
from datetime import datetime
from pathlib import Path

class JSONFormatter(logging.Formatter):
    """Formatter que gera logs em formato JSON"""
    
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "device_id": getattr(record, 'device_id', 'unknown'),
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Adicionar item_uid se disponível
        if hasattr(record, 'item_uid'):
            log_data["item_uid"] = record.item_uid
        
        # Adicionar exception se houver
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Adicionar campos extras
        if hasattr(record, 'extra_data'):
            log_data["extra"] = record.extra_data
        
        return json.dumps(log_data, ensure_ascii=False)

class TextFormatter(logging.Formatter):
    """Formatter para logs em texto simples"""
    
    def format(self, record):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        device_id = getattr(record, 'device_id', 'unknown')
        item_uid = getattr(record, 'item_uid', '')
        
        base = f"[{timestamp}] [{record.levelname}] [{device_id}]"
        
        if item_uid:
            base += f" [{item_uid[:8]}]"
        
        base += f" {record.getMessage()}"
        
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        
        return base

def setup_logging(config):
    """
    Configura logging estruturado
    
    Args:
        config: Dicionário de configuração
    
    Returns:
        Logger configurado
    """
    # Criar diretório de logs
    log_file = Path(config['logging']['file'])
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Configurar logger raiz
    logger = logging.getLogger()
    logger.setLevel(config['logging']['level'])
    
    # Limpar handlers existentes
    logger.handlers.clear()
    
    # Handler para arquivo
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    
    if config['logging']['format'] == 'json':
        file_handler.setFormatter(JSONFormatter())
    else:
        file_handler.setFormatter(TextFormatter())
    
    logger.addHandler(file_handler)
    
    # Handler para console (sempre texto)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(TextFormatter())
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    
    # Adicionar device_id a todos os logs
    device_id = config['device_id']
    
    # Criar adapter para injetar device_id
    class DeviceAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            # Adicionar device_id ao record
            if 'extra' not in kwargs:
                kwargs['extra'] = {}
            kwargs['extra']['device_id'] = device_id
            return msg, kwargs
    
    # Retornar adapter
    return DeviceAdapter(logger, {'device_id': device_id})

def get_logger(name, device_id='unknown', item_uid=None):
    """
    Retorna logger com contexto
    
    Args:
        name: Nome do módulo
        device_id: ID do dispositivo
        item_uid: UID do item (opcional)
    
    Returns:
        Logger com contexto
    """
    logger = logging.getLogger(name)
    
    class ContextAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            if 'extra' not in kwargs:
                kwargs['extra'] = {}
            kwargs['extra']['device_id'] = device_id
            if item_uid:
                kwargs['extra']['item_uid'] = item_uid
            return msg, kwargs
    
    return ContextAdapter(logger, {
        'device_id': device_id,
        'item_uid': item_uid
    })
