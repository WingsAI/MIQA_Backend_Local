#!/usr/bin/env python3
"""
Preparação para Teste de Failover
Cria 10 imagens únicas e prepara o sistema
"""

import shutil
import sqlite3
from pathlib import Path
from db.repository import QueueRepository

def prepare_failover_test():
    print("🔄 PREPARAÇÃO PARA TESTE DE FAILOVER")
    print("=" * 70)
    print()
    
    # 1. Limpar banco
    print("1️⃣  Limpando banco de dados...")
    conn = sqlite3.connect('./db/miqa.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM queue_items')
    cursor.execute('DELETE FROM metrics_events')
    conn.commit()
    conn.close()
    print("   ✅ Banco limpo")
    print()
    
    # 2. Setar estado ONLINE
    print("2️⃣  Configurando estado ONLINE...")
    repo = QueueRepository('./db/miqa.db')
    repo.set_system_state('connectivity_state', 'ONLINE')
    print("   ✅ Estado: ONLINE")
    print()
    
    # 3. Criar 10 imagens únicas
    print("3️⃣  Criando 10 imagens de teste...")
    source = Path('watch/mri/Te-piTr_0001.jpg')
    
    if not source.exists():
        print(f"   ❌ Imagem fonte não encontrada: {source}")
        print("   Copie uma imagem MRI para watch/mri/Te-piTr_0001.jpg")
        return
    
    created = []
    for i in range(10):
        dest = Path(f'watch/mri/failover_test_{i:02d}.jpg')
        
        # Copiar
        shutil.copy2(source, dest)
        
        # Adicionar bytes únicos para UID diferente
        with open(dest, 'ab') as f:
            unique_data = f'\n# Failover test image {i}\n'.encode('utf-8')
            f.write(unique_data)
        
        created.append(dest.name)
    
    print(f"   ✅ {len(created)} imagens criadas:")
    for name in created:
        print(f"      - {name}")
    print()
    
    # 4. Verificar configuração
    print("4️⃣  Verificando configuração...")
    import yaml
    with open('config/config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    mode = config.get('mode', 'AUTO')
    if mode != 'AUTO':
        print(f"   ⚠️  Modo está em '{mode}', deveria ser 'AUTO'")
        print("   Edite config/config.yaml e mude para: mode: \"AUTO\"")
    else:
        print("   ✅ Modo: AUTO")
    print()
    
    # 5. Instruções finais
    print("=" * 70)
    print("✅ PREPARAÇÃO COMPLETA!")
    print("=" * 70)
    print()
    print("📋 PRÓXIMOS PASSOS:")
    print()
    print("1. Iniciar workers em terminais separados:")
    print("   Terminal 1: python main.py listener")
    print("   Terminal 2: python main.py connectivity-manager")
    print("   Terminal 3: python main.py cloud-worker")
    print("   Terminal 4: python main.py local-worker")
    print()
    print("2. Aguardar 15-20 segundos (File Listener detectar)")
    print()
    print("3. Verificar status:")
    print("   python main.py status")
    print()
    print("4. Quando ver 3-5 imagens processadas na cloud:")
    print("   DESLIGAR INTERNET (WiFi ou cabo)")
    print()
    print("5. Aguardar failover automático (~10-15s)")
    print()
    print("6. Verificar que Local Worker assumiu:")
    print("   python main.py status")
    print()
    print("7. Aguardar todas as 10 serem processadas")
    print()
    print("8. Verificar resultados:")
    print("   ls results/online/   # Processadas antes")
    print("   ls results/offline/  # Processadas depois")
    print()
    print("=" * 70)
    print()
    print("📖 Guia completo: docs/TESTE_FAILOVER.md")
    print()

if __name__ == '__main__':
    prepare_failover_test()
