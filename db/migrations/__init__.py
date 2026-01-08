"""
Sistema de migrations simples para SQLite
"""

import sqlite3
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def run_migrations(db_path="./db/miqa.db"):
    """
    Executa migrations simples por versão
    
    Args:
        db_path: Caminho do banco de dados SQLite
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Inicializando banco de dados: {db_path}")
    
    # Conectar ao banco
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Criar tabela de controle de migrations (se não existir)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT
            )
        """)
        conn.commit()
        
        # Verificar versão atual
        cursor.execute("SELECT COALESCE(MAX(version), 0) FROM migrations")
        current_version = cursor.fetchone()[0]
        logger.info(f"Versão atual do banco: {current_version}")
        
        # Buscar migrations pendentes
        migrations_dir = Path(__file__).parent
        migration_files = sorted(migrations_dir.glob("*.sql"))
        
        if not migration_files:
            logger.warning("Nenhum arquivo de migration encontrado!")
            return
        
        # Aplicar migrations pendentes
        applied_count = 0
        for migration_file in migration_files:
            # Extrair versão do nome do arquivo (ex: 001_initial.sql -> 1)
            try:
                version = int(migration_file.stem.split("_")[0])
            except (ValueError, IndexError):
                logger.warning(f"Nome de arquivo inválido, ignorando: {migration_file.name}")
                continue
            
            if version > current_version:
                logger.info(f"Aplicando migration {version}: {migration_file.name}")
                
                # Ler e executar SQL
                with open(migration_file, 'r', encoding='utf-8') as f:
                    sql_script = f.read()
                
                try:
                    cursor.executescript(sql_script)
                    conn.commit()
                    applied_count += 1
                    logger.info(f"✅ Migration {version} aplicada com sucesso!")
                    
                except sqlite3.Error as e:
                    logger.error(f"❌ Erro ao aplicar migration {version}: {e}")
                    conn.rollback()
                    raise
        
        if applied_count == 0:
            logger.info("✅ Banco de dados já está atualizado!")
        else:
            logger.info(f"✅ {applied_count} migration(s) aplicada(s) com sucesso!")
    
    finally:
        conn.close()

def get_db_version(db_path="./db/miqa.db"):
    """
    Retorna a versão atual do banco de dados
    
    Args:
        db_path: Caminho do banco de dados
    
    Returns:
        int: Versão atual
    """
    db_path = Path(db_path)
    
    if not db_path.exists():
        return 0
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COALESCE(MAX(version), 0) FROM migrations")
        version = cursor.fetchone()[0]
        return version
    except sqlite3.OperationalError:
        # Tabela migrations não existe
        return 0
    finally:
        conn.close()

if __name__ == "__main__":
    # Permitir executar diretamente
    logging.basicConfig(level=logging.INFO)
    run_migrations()
