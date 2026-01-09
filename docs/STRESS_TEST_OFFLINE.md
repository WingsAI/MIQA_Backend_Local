# 🧪 Teste de Stress - Modo OFFLINE (Local)

## 🎯 Objetivo
Testar performance do processamento LOCAL com 100/500/1000 imagens

---

## 📋 Preparação

### 1. Parar Cloud Worker
```bash
# Pressione Ctrl+C no terminal do cloud-worker
```

### 2. Forçar Modo OFFLINE
Edite `config/config.yaml`:
```yaml
mode: "FORCED_OFFLINE"  # Mude de AUTO para FORCED_OFFLINE
```

### 3. Reiniciar Workers
```bash
# Terminal 1: File Listener
python main.py listener

# Terminal 2: Local Worker
python main.py local-worker

# NÃO rodar:
# - connectivity-manager (não precisa)
# - cloud-worker (não usar)
```

---

## 🚀 Executar Testes

### Teste 1: 100 imagens
```bash
python stress_test.py 100
```

### Teste 2: 500 imagens
```bash
python stress_test.py 500
```

### Teste 3: 1000 imagens
```bash
python stress_test.py 1000
```

---

## 📊 Resultados Esperados

### **Exemplo de saída:**

```
🔥 TESTE DE STRESS - Backend Local MIQA
======================================================================
📁 Imagem original: Te-piTr_0001.jpg
📊 Número de cópias: 100
📂 Diretório: watch\mri

🧹 Limpando banco de dados...
✅ Banco limpo

📋 FASE 1: Duplicando imagens (com UIDs únicos)...
  Copiadas: 100/100
✅ 100 imagens copiadas em 0.45s

📋 FASE 2: Aguardando File Listener detectar...
  (aguardando 15 segundos para estabilização)
✅ 100 imagens detectadas no banco

📋 FASE 3: Aguardando processamento...
  Aguardando 100 imagens serem processadas...
  Processadas: 10/100 | Pendentes: 90 | Falhas: 0 | Taxa: 0.50 img/s | ETA: 180s
  Processadas: 25/100 | Pendentes: 75 | Falhas: 0 | Taxa: 0.52 img/s | ETA: 144s
  Processadas: 50/100 | Pendentes: 50 | Falhas: 0 | Taxa: 0.54 img/s | ETA: 93s
  Processadas: 75/100 | Pendentes: 25 | Falhas: 0 | Taxa: 0.55 img/s | ETA: 45s
  Processadas: 100/100 | Pendentes: 0 | Falhas: 0 | Taxa: 0.56 img/s | ETA: 0s
✅ Todas as 100 imagens finalizadas!
   Processadas: 100 | Falhas: 0

📋 FASE 4: Coletando estatísticas...

📋 FASE 5: Coletando resultados de processamento...
✅ 100 resultados coletados
   Score médio: 60.52
   Score min/max: 60.29 / 60.79
💾 Resultados agregados salvos em: stress_test_results_20260109_150500.json
   (100 resultados em 1 arquivo)

======================================================================
📊 RESULTADOS DO TESTE DE STRESS
======================================================================

⏱️  TEMPO DE PROCESSAMENTO: 178.50s (2.98 min)
   (Tempo de cópia não incluído: 0.45s)

📈 PERFORMANCE:
   - Tempo médio por imagem: 1.785s
   - Imagens por segundo: 0.56
   - Imagens por minuto: 33.61

✅ PROCESSAMENTO:
   - Total processadas: 100/100
   - Processadas na nuvem: 0
   - Processadas localmente: 100
   - Falhas: 0

🎯 QUALIDADE (Scores):
   - Score médio: 60.52
   - Score mín/máx: 60.29 / 60.79

💾 Métricas salvas em: stress_test_metrics_20260109_150500.json

======================================================================
```

---

## 📈 Benchmarks Esperados (Local)

| Imagens | Tempo Esperado | Taxa Esperada |
|---------|----------------|---------------|
| 100     | ~3-5 min       | 20-30 img/min |
| 500     | ~15-25 min     | 20-30 img/min |
| 1000    | ~30-50 min     | 20-30 img/min |

---

## 🔍 O que Observar

### **Performance:**
- Taxa de processamento (img/s) deve ser constante
- Não deve degradar com mais imagens
- Tempo médio por imagem deve ser estável

### **Recursos:**
- Uso de CPU (deve ficar alto)
- Uso de memória (não deve crescer muito)
- Uso de disco (results/offline/ vai crescer)

### **Qualidade:**
- Scores devem ser consistentes
- Não deve haver falhas
- Todos os resultados devem ser salvos

---

## 📁 Arquivos Gerados

### **Métricas:**
```
stress_test_metrics_TIMESTAMP.json
```

Contém:
- Tempo de processamento
- Taxa (img/s e img/min)
- Estatísticas de scores
- Contadores

### **Resultados Agregados:**
```
stress_test_results_TIMESTAMP.json
```

Contém:
- Todos os 100/500/1000 resultados em 1 arquivo
- Informações do teste
- Scores individuais

---

## 🧹 Limpeza

Após o teste, o script pergunta se quer limpar.

**Manual:**
```bash
# Remover imagens de teste
rm watch/mri/stress_test_*.jpg

# Limpar resultados
rm results/offline/*.json

# Limpar banco
python -c "import sqlite3; conn = sqlite3.connect('./db/miqa.db'); cursor = conn.cursor(); cursor.execute('DELETE FROM queue_items'); conn.commit(); print('✅ Limpo')"
```

---

## 🔄 Voltar para Modo AUTO

Após os testes, edite `config/config.yaml`:
```yaml
mode: "AUTO"  # Voltar para AUTO
```

---

**Última atualização:** 2026-01-09 15:05
