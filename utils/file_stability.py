"""
Verificação de estabilidade de arquivo
Garante que arquivo não está sendo escrito antes de processar
"""

import time
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def is_file_stable(path: Path, checks=5, interval=1.0, timeout=30) -> bool:
    """
    Verifica se arquivo está estável (não está sendo escrito)
    
    Args:
        path: Caminho do arquivo
        checks: Número de verificações consecutivas
        interval: Intervalo entre verificações (segundos)
        timeout: Timeout máximo (segundos)
    
    Returns:
        True se arquivo está estável, False caso contrário
    """
    if not isinstance(path, Path):
        path = Path(path)
    
    start_time = time.time()
    previous_size = None
    previous_mtime = None
    stable_count = 0
    
    logger.debug(f"Verificando estabilidade de: {path}")
    
    for i in range(checks * 2):  # Permitir mais tentativas
        # Verificar timeout
        if time.time() - start_time > timeout:
            logger.warning(f"Timeout ao verificar estabilidade: {path}")
            return False
        
        try:
            # Verificar se arquivo existe
            if not path.exists():
                logger.warning(f"Arquivo não encontrado: {path}")
                return False
            
            # Obter informações do arquivo
            stat = path.stat()
            current_size = stat.st_size
            current_mtime = stat.st_mtime
            
            # Comparar com verificação anterior
            if previous_size is not None and previous_mtime is not None:
                if current_size == previous_size and current_mtime == previous_mtime:
                    stable_count += 1
                    logger.debug(f"Arquivo estável ({stable_count}/{checks}): {path}")
                    
                    # Se estável por N verificações consecutivas
                    if stable_count >= checks:
                        logger.info(f"✅ Arquivo estável confirmado: {path}")
                        return True
                else:
                    # Arquivo mudou, resetar contador
                    logger.debug(f"Arquivo ainda mudando: {path} (size: {previous_size}->{current_size})")
                    stable_count = 0
            
            # Atualizar valores anteriores
            previous_size = current_size
            previous_mtime = current_mtime
            
            # Aguardar próxima verificação
            time.sleep(interval)
            
        except FileNotFoundError:
            logger.warning(f"Arquivo desapareceu durante verificação: {path}")
            return False
        except PermissionError:
            logger.warning(f"Sem permissão para acessar: {path}")
            return False
        except Exception as e:
            logger.error(f"Erro ao verificar estabilidade de {path}: {e}")
            return False
    
    # Se chegou aqui, não conseguiu confirmar estabilidade
    logger.warning(f"Não foi possível confirmar estabilidade: {path}")
    return False

def wait_for_file_stable(path: Path, max_wait=60) -> bool:
    """
    Aguarda até arquivo ficar estável
    
    Args:
        path: Caminho do arquivo
        max_wait: Tempo máximo de espera (segundos)
    
    Returns:
        True se ficou estável, False se timeout
    """
    logger.info(f"Aguardando arquivo ficar estável: {path}")
    
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        if is_file_stable(path, checks=3, interval=0.5, timeout=10):
            return True
        
        # Aguardar um pouco antes de tentar novamente
        time.sleep(2)
    
    logger.error(f"Timeout aguardando estabilidade: {path}")
    return False
