#!/usr/bin/env python3
"""
Backend Local MIQA - Sistema de processamento offline/online
CLI principal para gerenciar todos os serviços
"""

import click
import asyncio
import logging
import yaml
from pathlib import Path

# Importar configuração de logging
from utils.logging_config import setup_logging

# Carregar configuração
def load_config():
    config_path = Path("config/config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)

config = load_config()
logger = setup_logging(config)

@click.group()
@click.version_option(version="1.0.0")
def cli():
    """
    Backend Local MIQA - Sistema de processamento offline/online
    
    Sistema edge para processamento de imagens médicas com fallback offline.
    """
    pass

@cli.command()
def listener():
    """
    Monitora pasta e detecta novas imagens
    
    Monitora o diretório configurado em 'directories.watch' e registra
    novas imagens no banco de dados para processamento.
    """
    from edge.listener import FileListener
    
    click.echo("🔍 Iniciando File Listener...")
    click.echo(f"📁 Monitorando: {config['directories']['watch']}")
    
    listener = FileListener(config)
    listener.start()

@cli.command()
def dicom_receiver():
    """
    Recebe imagens via DICOM SCP (stub - não implementado ainda)
    
    Servidor DICOM SCP para receber imagens de equipamentos médicos.
    """
    from edge.dicom_receiver import DICOMReceiver
    
    click.echo("📡 Iniciando DICOM Receiver...")
    click.echo("⚠️  STUB: Implementação básica apenas")
    
    receiver = DICOMReceiver(config)
    receiver.start()

@cli.command()
def connectivity_manager():
    """
    Gerencia estado de conectividade com a nuvem
    
    Monitora a conectividade com a API de produção e atualiza
    o estado (ONLINE/OFFLINE/DEGRADED) no banco de dados.
    """
    from connectivity.manager import ConnectivityManager
    
    click.echo("🌐 Iniciando Connectivity Manager...")
    click.echo(f"🔗 Healthcheck: {config['cloud']['healthcheck_url']}")
    
    manager = ConnectivityManager(config)
    asyncio.run(manager.run())

@cli.command()
def cloud_worker():
    """
    Envia imagens para nuvem quando online
    
    Worker que monitora a fila e envia imagens pendentes
    para a API de produção quando há conectividade.
    """
    from cloud_client.worker import CloudWorker
    
    click.echo("☁️  Iniciando Cloud Worker...")
    click.echo(f"🚀 API: {config['cloud']['api_url']}")
    
    worker = CloudWorker(config)
    asyncio.run(worker.run())

@cli.command()
def local_worker():
    """
    Processa imagens localmente quando offline
    
    Worker que processa imagens localmente usando o algoritmo MIQA
    quando não há conectividade com a nuvem.
    """
    from local_processing.worker import LocalWorker
    
    click.echo("💻 Iniciando Local Worker...")
    click.echo(f"📊 Resultados: {config['directories']['results']}")
    
    worker = LocalWorker(config)
    worker.run()

@cli.command()
def metrics_exporter():
    """
    Exporta métricas (futuro)

    Exporta métricas acumuladas para a nuvem ou para arquivo local.
    """
    from metrics.exporter import MetricsExporter

    click.echo("📊 Iniciando Metrics Exporter...")

    exporter = MetricsExporter(config)
    exporter.run()

@cli.command()
def sync_worker():
    """
    Sincroniza resultados offline com API de produção

    Quando internet volta, envia JSONs de results/offline/
    para o endpoint configurado em sync.endpoint
    """
    from metrics.sync_worker import SyncWorker

    api_url = config['cloud']['api_url']
    endpoint = config.get('sync', {}).get('endpoint', '/api/v1/miqa/sync-offline')

    click.echo("🔄 Iniciando Sync Worker...")
    click.echo(f"API: {api_url}{endpoint}")

    worker = SyncWorker(config)
    worker.run()

@cli.command()
def init_db():
    """
    Inicializa banco de dados SQLite
    
    Cria o banco de dados e aplica todas as migrations necessárias.
    """
    from db.migrations import run_migrations
    
    click.echo("🗄️  Inicializando banco de dados...")
    click.echo(f"📁 Path: {config['database']['path']}")
    
    run_migrations(config['database']['path'])
    
    click.echo("✅ Banco de dados inicializado com sucesso!")

@cli.command()
@click.option('--all', is_flag=True, help='Inicia todos os serviços')
def start(all):
    """
    Inicia serviços (futuro: orquestrador)
    
    Inicia múltiplos serviços simultaneamente.
    """
    if all:
        click.echo("🚀 Iniciando todos os serviços...")
        click.echo("⚠️  Use supervisord ou systemd em produção")
        click.echo("")
        click.echo("Execute manualmente em terminais separados:")
        click.echo("  python main.py listener")
        click.echo("  python main.py connectivity-manager")
        click.echo("  python main.py cloud-worker")
        click.echo("  python main.py local-worker")
    else:
        click.echo("Use --all para iniciar todos os serviços")

@cli.command()
def status():
    """
    Mostra status do sistema
    
    Exibe informações sobre fila, conectividade e workers.
    """
    from db.repository import QueueRepository
    
    click.echo("📊 Status do Sistema")
    click.echo("=" * 50)
    
    repo = QueueRepository(config['database']['path'])
    
    # Estado de conectividade
    state = repo.get_system_state('connectivity_state')
    click.echo(f"🌐 Conectividade: {state or 'UNKNOWN'}")
    
    # Estatísticas da fila
    stats = repo.get_queue_stats()
    click.echo(f"\n📋 Fila:")
    click.echo(f"  Total de itens: {stats['total']}")
    click.echo(f"  Pendente cloud: {stats['pending_cloud']}")
    click.echo(f"  Pendente local: {stats['pending_local']}")
    click.echo(f"  Processados: {stats['completed']}")
    click.echo(f"  Falhas: {stats['failed']}")

if __name__ == "__main__":
    cli()
