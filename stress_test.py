#!/usr/bin/env python3
"""
Teste de Stress - Backend Local MIQA
Duplica imagem e processa em lote para medir performance
"""

import time
import shutil
import json
from pathlib import Path
from datetime import datetime
import sqlite3

def stress_test(
    source_image: str = "watch/mri/Te-piTr_0001.jpg",
    num_copies: int = 100,
    output_dir: str = "watch/mri"
):
    """
    Teste de stress do sistema
    
    Args:
        source_image: Imagem original
        num_copies: Número de cópias
        output_dir: Diretório de saída
    """
    print("🔥 TESTE DE STRESS - Backend Local MIQA")
    print("=" * 70)
    
    source_path = Path(source_image)
    output_path = Path(output_dir)
    
    # Verificar se imagem existe
    if not source_path.exists():
        print(f"❌ Imagem não encontrada: {source_image}")
        return
    
    print(f"📁 Imagem original: {source_path.name}")
    print(f"📊 Número de cópias: {num_copies}")
    print(f"📂 Diretório: {output_path}")
    print()
    
    # Limpar banco antes do teste
    print("🧹 Limpando banco de dados...")
    conn = sqlite3.connect('./db/miqa.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM queue_items')
    cursor.execute('DELETE FROM metrics_events')
    conn.commit()
    conn.close()
    print("✅ Banco limpo")
    print()
    
    # Métricas
    metrics = {
        'test_name': 'stress_test',
        'source_image': str(source_path),
        'num_copies': num_copies,
        'start_time': datetime.now().isoformat(),
        'copy_times': [],
        'processing_times': [],
        'total_time': 0,
        'avg_time_per_image': 0,
        'images_per_minute': 0,
        'images_per_second': 0
    }
    
    # Fase 1: Duplicar imagens
    print("📋 FASE 1: Duplicando imagens (com UIDs únicos)...")
    copy_start = time.time()
    
    copied_files = []
    for i in range(num_copies):
        # Nome único
        new_name = f"stress_test_{i:04d}.jpg"
        new_path = output_path / new_name
        
        # Copiar
        copy_file_start = time.time()
        shutil.copy2(source_path, new_path)
        
        # Adicionar bytes únicos no final para gerar UID diferente
        # Isso garante que cada imagem tenha um hash SHA256 único
        with open(new_path, 'ab') as f:
            # Adicionar número do índice como bytes no final
            unique_data = f"\n# Test image {i}\n".encode('utf-8')
            f.write(unique_data)
        
        copy_file_time = time.time() - copy_file_start
        
        copied_files.append(str(new_path))
        metrics['copy_times'].append(copy_file_time)
        
        if (i + 1) % 100 == 0:
            print(f"  Copiadas: {i + 1}/{num_copies}")
    
    copy_duration = time.time() - copy_start
    print(f"✅ {num_copies} imagens copiadas em {copy_duration:.2f}s")
    print()
    
    # Fase 2: Aguardar detecção
    print("📋 FASE 2: Aguardando File Listener detectar...")
    print("  (aguardando 15 segundos para estabilização)")
    time.sleep(15)
    
    # Verificar quantas foram detectadas
    conn = sqlite3.connect('./db/miqa.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM queue_items')
    detected = cursor.fetchone()[0]
    conn.close()
    
    print(f"✅ {detected} imagens detectadas no banco")
    
    if detected == 0:
        print("❌ Nenhuma imagem foi detectada!")
        print("   Verifique se o File Listener está rodando")
        return
    
    if detected < num_copies:
        print(f"⚠️  Apenas {detected}/{num_copies} imagens foram detectadas")
        print(f"   Continuando com {detected} imagens...")
    
    print()
    
    # Fase 3: Aguardar processamento
    print("📋 FASE 3: Aguardando processamento...")
    print(f"  Aguardando {detected} imagens serem processadas...")
    processing_start = time.time()
    
    last_processed = 0
    max_wait = 1800  # 30 minutos max
    check_interval = 2  # Verificar a cada 2s
    no_progress_count = 0
    max_no_progress = 30  # 60 segundos sem progresso = timeout
    
    while time.time() - processing_start < max_wait:
        conn = sqlite3.connect('./db/miqa.db')
        cursor = conn.cursor()
        
        # Contar processados (cloud ou local)
        cursor.execute("""
            SELECT COUNT(*) FROM queue_items 
            WHERE cloud_status = 'UPLOADED' OR local_status = 'DONE'
        """)
        processed = cursor.fetchone()[0]
        
        # Contar pendentes
        cursor.execute("""
            SELECT COUNT(*) FROM queue_items 
            WHERE (cloud_status IN ('PENDING', 'UPLOADING'))
            OR (local_status IN ('PENDING', 'PROCESSING'))
        """)
        pending = cursor.fetchone()[0]
        
        # Contar falhados
        cursor.execute("""
            SELECT COUNT(*) FROM queue_items 
            WHERE cloud_status = 'FAILED' OR local_status = 'FAILED'
        """)
        failed_count = cursor.fetchone()[0]
        
        conn.close()
        
        # Mostrar progresso
        if processed != last_processed:
            elapsed = time.time() - processing_start
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = detected - processed - failed_count
            eta = remaining / rate if rate > 0 else 0
            
            print(f"  Processadas: {processed}/{detected} | "
                  f"Pendentes: {pending} | "
                  f"Falhas: {failed_count} | "
                  f"Taxa: {rate:.2f} img/s | "
                  f"ETA: {eta:.0f}s")
            
            last_processed = processed
            no_progress_count = 0
        else:
            no_progress_count += 1
        
        # Se terminou (processadas + falhas = total detectado)
        total_finished = processed + failed_count
        if total_finished >= detected and pending == 0:
            print(f"✅ Todas as {detected} imagens finalizadas!")
            print(f"   Processadas: {processed} | Falhas: {failed_count}")
            break
        
        # Timeout sem progresso
        if no_progress_count >= max_no_progress:
            print(f"⚠️  Timeout: {no_progress_count * check_interval}s sem progresso")
            print(f"   Processadas até agora: {processed}/{detected}")
            break
        
        time.sleep(check_interval)
    
    processing_duration = time.time() - processing_start
    
    # Fase 4: Coletar estatísticas finais
    print()
    print("📋 FASE 4: Coletando estatísticas...")
    
    conn = sqlite3.connect('./db/miqa.db')
    cursor = conn.cursor()
    
    # Total processado
    cursor.execute("""
        SELECT COUNT(*) FROM queue_items 
        WHERE cloud_status = 'UPLOADED' OR local_status = 'DONE'
    """)
    total_processed = cursor.fetchone()[0]
    
    # Processados na nuvem
    cursor.execute("""
        SELECT COUNT(*) FROM queue_items 
        WHERE cloud_status = 'UPLOADED'
    """)
    cloud_processed = cursor.fetchone()[0]
    
    # Processados localmente
    cursor.execute("""
        SELECT COUNT(*) FROM queue_items 
        WHERE local_status = 'DONE' AND cloud_status != 'UPLOADED'
    """)
    local_processed = cursor.fetchone()[0]
    
    # Falhas
    cursor.execute("""
        SELECT COUNT(*) FROM queue_items 
        WHERE cloud_status = 'FAILED' OR local_status = 'FAILED'
    """)
    failed = cursor.fetchone()[0]
    
    conn.close()
    
    # Fase 5: Coletar resultados individuais
    print()
    print("📋 FASE 5: Coletando resultados de processamento...")
    
    results_online = Path("./results/online")
    results_offline = Path("./results/offline")
    
    all_results = []
    scores = []
    
    # Coletar resultados online
    if results_online.exists():
        for result_file in results_online.glob("*.json"):
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                    all_results.append(result)
                    
                    # Extrair score
                    if 'result' in result and 'score' in result['result']:
                        scores.append(result['result']['score'])
                    elif 'score' in result:
                        scores.append(result['score'])
            except Exception as e:
                print(f"  ⚠️  Erro ao ler {result_file.name}: {e}")
    
    # Coletar resultados offline
    if results_offline.exists():
        for result_file in results_offline.glob("*.json"):
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                    all_results.append(result)
                    
                    # Extrair score
                    if 'score' in result:
                        scores.append(result['score'])
            except Exception as e:
                print(f"  ⚠️  Erro ao ler {result_file.name}: {e}")
    
    print(f"✅ {len(all_results)} resultados coletados")
    
    # Calcular estatísticas de scores
    if scores:
        avg_score = sum(scores) / len(scores)
        min_score = min(scores)
        max_score = max(scores)
        print(f"   Score médio: {avg_score:.2f}")
        print(f"   Score min/max: {min_score:.2f} / {max_score:.2f}")
    
    # Calcular métricas finais (SEM tempo de cópia)
    avg_time = processing_duration / total_processed if total_processed > 0 else 0
    images_per_second = total_processed / processing_duration if processing_duration > 0 else 0
    images_per_minute = images_per_second * 60
    
    metrics['end_time'] = datetime.now().isoformat()
    metrics['copy_duration'] = copy_duration
    metrics['processing_duration'] = processing_duration
    metrics['total_processed'] = total_processed
    metrics['cloud_processed'] = cloud_processed
    metrics['local_processed'] = local_processed
    metrics['failed'] = failed
    metrics['avg_time_per_image'] = avg_time
    metrics['images_per_second'] = images_per_second
    metrics['images_per_minute'] = images_per_minute
    metrics['total_results_collected'] = len(all_results)
    
    # Adicionar estatísticas de scores
    if scores:
        metrics['score_stats'] = {
            'avg': avg_score,
            'min': min_score,
            'max': max_score,
            'count': len(scores)
        }
    
    # Salvar métricas principais
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    metrics_file = Path(f"stress_test_metrics_{timestamp}.json")
    with open(metrics_file, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    
    # Salvar resultados agregados (todos os JSONs em um só)
    if all_results:
        aggregated_file = Path(f"stress_test_results_{timestamp}.json")
        aggregated_data = {
            'test_info': {
                'timestamp': timestamp,
                'num_images': num_copies,
                'total_processed': total_processed,
                'total_results': len(all_results)
            },
            'results': all_results
        }
        
        with open(aggregated_file, 'w', encoding='utf-8') as f:
            json.dump(aggregated_data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Resultados agregados salvos em: {aggregated_file}")
        print(f"   ({len(all_results)} resultados em 1 arquivo)")
    
    # Exibir resultados
    print()
    print("=" * 70)
    print("📊 RESULTADOS DO TESTE DE STRESS")
    print("=" * 70)
    print()
    print(f"⏱️  TEMPO DE PROCESSAMENTO: {processing_duration:.2f}s ({processing_duration/60:.2f} min)")
    print(f"   (Tempo de cópia não incluído: {copy_duration:.2f}s)")
    print()
    print(f"📈 PERFORMANCE:")
    print(f"   - Tempo médio por imagem: {avg_time:.3f}s")
    print(f"   - Imagens por segundo: {images_per_second:.2f}")
    print(f"   - Imagens por minuto: {images_per_minute:.2f}")
    print()
    print(f"✅ PROCESSAMENTO:")
    print(f"   - Total processadas: {total_processed}/{detected}")
    print(f"   - Processadas na nuvem: {cloud_processed}")
    print(f"   - Processadas localmente: {local_processed}")
    print(f"   - Falhas: {failed}")
    print()
    if scores:
        print(f"🎯 QUALIDADE (Scores):")
        print(f"   - Score médio: {avg_score:.2f}")
        print(f"   - Score mín/máx: {min_score:.2f} / {max_score:.2f}")
        print()
    print(f"💾 Métricas salvas em: {metrics_file}")
    print()
    print("=" * 70)
    
    # Limpar arquivos de teste
    print()
    cleanup = input("🧹 Limpar arquivos de teste? (s/n): ")
    if cleanup.lower() == 's':
        print("Removendo arquivos...")
        for file_path in copied_files:
            try:
                Path(file_path).unlink()
            except:
                pass
        print("✅ Arquivos removidos")

if __name__ == "__main__":
    import sys
    
    # Argumentos
    num_copies = 100
    if len(sys.argv) > 1:
        num_copies = int(sys.argv[1])
    
    stress_test(num_copies=num_copies)
