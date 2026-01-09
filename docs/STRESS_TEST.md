# 🔥 Teste de Stress - Backend Local MIQA

Script para testar performance e capacidade do sistema com múltiplas imagens simultâneas.

---

## 🎯 O que o teste faz:

1. **Duplica** a imagem original N vezes
2. **Aguarda** o File Listener detectar
3. **Monitora** o processamento em tempo real
4. **Coleta** métricas detalhadas
5. **Gera** relatório completo

---

## 🚀 Como Usar

### **Teste com 100 imagens (padrão):**
```bash
python stress_test.py
```

### **Teste com quantidade customizada:**
```bash
# 50 imagens
python stress_test.py 50

# 500 imagens
python stress_test.py 500

# 1000 imagens
python stress_test.py 1000
```

---

## 📋 Pré-requisitos

1. **Imagem de teste existe:**
   ```bash
   ls watch/mri/Te-piTr_0001.jpg
   ```

2. **Workers rodando:**
   ```bash
   # Terminal 1
   python main.py listener
   
   # Terminal 2
   python main.py connectivity-manager
   
   # Terminal 3
   python main.py cloud-worker
   
   # Terminal 4 (opcional)
   python main.py local-worker
   ```

3. **Sistema ONLINE** (para testar cloud) ou **OFFLINE** (para testar local)

---

## 📊 Métricas Coletadas

### **Durante o teste:**
- ✅ Progresso em tempo real
- ✅ Taxa de processamento (img/s)
- ✅ ETA (tempo estimado)
- ✅ Imagens pendentes

### **Ao final:**
```
📊 RESULTADOS DO TESTE DE STRESS
==================================================

⏱️  TEMPO TOTAL: 125.45s (2.09 min)
   - Cópia: 5.23s
   - Processamento: 120.22s

📈 PERFORMANCE:
   - Tempo médio por imagem: 1.202s
   - Imagens por segundo: 0.83
   - Imagens por minuto: 49.87

✅ PROCESSAMENTO:
   - Total processadas: 100/100
   - Processadas na nuvem: 100
   - Processadas localmente: 0
   - Falhas: 0
```

### **Arquivo JSON gerado:**
```json
{
  "test_name": "stress_test",
  "source_image": "watch/mri/Te-piTr_0001.jpg",
  "num_copies": 100,
  "start_time": "2026-01-09T14:35:00",
  "end_time": "2026-01-09T14:37:05",
  "copy_duration": 5.23,
  "processing_duration": 120.22,
  "total_time": 125.45,
  "total_processed": 100,
  "cloud_processed": 100,
  "local_processed": 0,
  "failed": 0,
  "avg_time_per_image": 1.202,
  "images_per_second": 0.83,
  "images_per_minute": 49.87
}
```

---

## 🔍 Casos de Teste

### **1. Teste Cloud (ONLINE)**
```bash
# Garantir que está ONLINE
python -c "from db.repository import QueueRepository; repo = QueueRepository('./db/miqa.db'); repo.set_system_state('connectivity_state', 'ONLINE'); print('✅ ONLINE')"

# Rodar teste
python stress_test.py 100
```

**Esperado:**
- `cloud_processed = 100`
- `local_processed = 0`

---

### **2. Teste Local (OFFLINE)**
```bash
# Forçar OFFLINE
# Editar config.yaml: mode: "FORCED_OFFLINE"

# Rodar teste
python stress_test.py 100
```

**Esperado:**
- `cloud_processed = 0`
- `local_processed = 100`

---

### **3. Teste de Capacidade Máxima**
```bash
# Testar com 1000 imagens
python stress_test.py 1000
```

**Observar:**
- Taxa de processamento cai?
- Memória aumenta muito?
- Sistema fica lento?

---

### **4. Teste de Concorrência**
```bash
# Rodar 2 testes simultâneos em terminais diferentes
# Terminal 1:
python stress_test.py 50

# Terminal 2 (ao mesmo tempo):
python stress_test.py 50
```

**Observar:**
- Sistema processa 100 total?
- Há conflitos?
- Performance cai pela metade?

---

## 📈 Benchmarks Esperados

### **Cloud Worker (ONLINE):**
- **Bom:** > 30 img/min
- **Médio:** 15-30 img/min
- **Ruim:** < 15 img/min

### **Local Worker (OFFLINE):**
- **Bom:** > 10 img/min
- **Médio:** 5-10 img/min
- **Ruim:** < 5 img/min

---

## 🐛 Troubleshooting

### **Problema: Teste trava em "Aguardando processamento"**

**Causa:** Workers não estão rodando

**Solução:**
```bash
# Verificar se workers estão ativos
ps aux | grep "main.py"

# Reiniciar workers
python main.py listener &
python main.py cloud-worker &
```

---

### **Problema: "Imagem não encontrada"**

**Causa:** Arquivo de origem não existe

**Solução:**
```bash
# Verificar se existe
ls watch/mri/Te-piTr_0001.jpg

# Ou usar outra imagem
# Editar stress_test.py linha 13:
source_image: str = "watch/mri/SUA_IMAGEM.jpg"
```

---

### **Problema: Muitas falhas**

**Causa:** API retornando erro ou sistema sobrecarregado

**Solução:**
```bash
# Ver logs
tail -f logs/miqa.log | grep "FAILED"

# Reduzir concorrência em config.yaml:
max_concurrent_uploads: 2  # Era 5
max_concurrent_processing: 1  # Era 2
```

---

## 🧹 Limpeza Após Teste

O script pergunta se quer limpar os arquivos de teste ao final.

**Manual:**
```bash
# Remover imagens de teste
rm watch/mri/stress_test_*.jpg

# Limpar banco
python -c "import sqlite3; conn = sqlite3.connect('./db/miqa.db'); cursor = conn.cursor(); cursor.execute('DELETE FROM queue_items'); conn.commit(); print('✅ Limpo')"

# Limpar resultados
rm results/online/*.json
rm results/offline/*.json
```

---

## 📊 Comparar Resultados

```bash
# Ver todos os testes
ls stress_test_results_*.json

# Comparar 2 testes
python -c "
import json
from pathlib import Path

files = sorted(Path('.').glob('stress_test_results_*.json'))
if len(files) >= 2:
    with open(files[-2]) as f1, open(files[-1]) as f2:
        test1 = json.load(f1)
        test2 = json.load(f2)
    
    print(f'Teste 1: {test1[\"images_per_minute\"]:.2f} img/min')
    print(f'Teste 2: {test2[\"images_per_minute\"]:.2f} img/min')
    diff = ((test2['images_per_minute'] - test1['images_per_minute']) / test1['images_per_minute']) * 100
    print(f'Diferença: {diff:+.1f}%')
"
```

---

**Última atualização:** 2026-01-09 14:35
