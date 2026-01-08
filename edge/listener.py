"""
File Listener - Monitora pasta e detecta novas imagens
"""

import time
import hashlib
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import logging

from db.repository import QueueRepository
from utils.file_stability import is_file_stable

logger = logging.getLogger(__name__)

class ImageFileHandler(FileSystemEventHandler):
    """Handler para eventos de arquivo"""
    
    def __init__(self, repository: QueueRepository, config: dict):
        self.repository = repository
        self.config = config
        self.valid_extensions = {'.jpg', '.jpeg', '.png', '.dcm', '.dicom'}
        self.processed_files = set()  # Evitar processar múltiplas vezes
    
    def on_created(self, event):
        """Callback quando arquivo é criado"""
        if event.is_directory:
            return
        
        self._handle_file(Path(event.src_path))
    
    def on_modified(self, event):
        """Callback quando arquivo é modificado"""
        if event.is_directory:
            return
        
        # Só processar se ainda não foi processado
        path = Path(event.src_path)
        if str(path) not in self.processed_files:
            self._handle_file(path)
    
    def on_moved(self, event):
        """Callback quando arquivo é movido para pasta"""
        if event.is_directory:
            return
        
        self._handle_file(Path(event.dest_path))
    
    def _handle_file(self, path: Path):
        """
        Processa arquivo detectado
        
        Args:
            path: Caminho do arquivo
        """
        # Verificar extensão
        if path.suffix.lower() not in self.valid_extensions:
            logger.debug(f"Extensão não suportada, ignorando: {path}")
            return
        
        # Evitar processar múltiplas vezes
        if str(path) in self.processed_files:
            logger.debug(f"Arquivo já processado, ignorando: {path}")
            return
        
        logger.info(f"📁 Arquivo detectado: {path}")
        
        # Verificar se arquivo está estável
        stability_config = self.config.get('file_stability', {})
        if not is_file_stable(
            path,
            checks=stability_config.get('checks', 5),
            interval=stability_config.get('interval', 1.0),
            timeout=stability_config.get('timeout', 30)
        ):
            logger.warning(f"⚠️  Arquivo não estável ou timeout, ignorando: {path}")
            return
        
        # Gerar item_uid
        try:
            item_uid = self._generate_uid(path)
            logger.debug(f"UID gerado: {item_uid[:16]}...")
            
            # Registrar no banco
            meta = {
                'modality': self._detect_modality(path),
                'device': self.config.get('device_id', 'unknown'),
                'exam_type': 'unknown'
            }
            
            self.repository.upsert_item(
                item_uid=item_uid,
                path=str(path.absolute()),
                source_type='LISTENER',
                meta=meta
            )
            
            # Marcar como processado
            self.processed_files.add(str(path))
            
            logger.info(f"✅ Item registrado: {item_uid[:16]}... ({path.name})")
            
        except Exception as e:
            logger.error(f"❌ Erro ao processar arquivo {path}: {e}", exc_info=True)
    
    def _generate_uid(self, path: Path) -> str:
        """
        Gera UID único baseado em hash do arquivo
        
        Args:
            path: Caminho do arquivo
        
        Returns:
            UID (SHA256 hex)
        """
        hasher = hashlib.sha256()
        
        # Hash incremental para arquivos grandes
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):  # 64KB chunks
                hasher.update(chunk)
        
        return hasher.hexdigest()
    
    def _detect_modality(self, path: Path) -> str:
        """
        Tenta detectar modalidade da imagem
        
        Args:
            path: Caminho do arquivo
        
        Returns:
            Modalidade detectada ou 'unknown'
        """
        # Por enquanto, retorna unknown
        # TODO: Implementar detecção via DICOM tags ou nome do arquivo
        
        filename_lower = path.name.lower()
        
        if 'mri' in filename_lower or 'rm' in filename_lower:
            return 'mri'
        elif 'ct' in filename_lower or 'tc' in filename_lower:
            return 'ct'
        elif 'us' in filename_lower or 'ultra' in filename_lower:
            return 'us'
        elif 'xray' in filename_lower or 'rx' in filename_lower:
            return 'xray'
        else:
            return 'unknown'

class FileListener:
    """Listener principal que monitora pasta"""
    
    def __init__(self, config: dict):
        self.config = config
        self.watch_dir = Path(config['directories']['watch'])
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        
        self.repository = QueueRepository(config['database']['path'])
        self.observer = Observer()
        
        logger.info(f"FileListener inicializado")
        logger.info(f"Monitorando: {self.watch_dir.absolute()}")
    
    def start(self):
        """Inicia monitoramento"""
        # Criar handler
        event_handler = ImageFileHandler(self.repository, self.config)
        
        # Configurar observer
        self.observer.schedule(
            event_handler,
            str(self.watch_dir),
            recursive=True
        )
        
        # Iniciar
        self.observer.start()
        logger.info(f"🔍 Monitoramento iniciado: {self.watch_dir}")
        
        # Processar arquivos existentes
        self._process_existing_files(event_handler)
        
        try:
            # Loop principal
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Parando monitoramento...")
            self.observer.stop()
        
        self.observer.join()
        logger.info("Monitoramento finalizado")
    
    def _process_existing_files(self, handler: ImageFileHandler):
        """
        Processa arquivos que já existem na pasta
        
        Args:
            handler: Handler de eventos
        """
        logger.info("Verificando arquivos existentes...")
        
        count = 0
        for file_path in self.watch_dir.rglob('*'):
            if file_path.is_file():
                handler._handle_file(file_path)
                count += 1
        
        logger.info(f"Processados {count} arquivos existentes")
