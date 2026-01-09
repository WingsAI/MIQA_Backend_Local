# 🔄 TESTE DE FAILOVER - Cloud → Local

## 🎯 Objetivo
Testar o roteamento inteligente: começar processando na nuvem (ONLINE) e, ao desligar a internet, continuar processando localmente (OFFLINE) sem perder imagens.

---

## ✅ VERIFICAÇÃO PRÉ-TESTE

### **1. Sistema está preparado?**

**SIM!** ✅ O sistema já tem:
- ✅ Connectivity Manager (detecta perda de internet)
- ✅ Cloud Worker (processa quando ONLINE)
- ✅ Local Worker (processa quando OFFLINE ou cloud falha)
- ✅ Fallback automático (local processa se cloud falhar 3x)

### **2. Componentes necessários:**
- ✅ File Listener (detecta imagens)
- ✅ Connectivity Manager (monitora internet)
- ✅ Cloud Worker (tenta enviar para API)
- ✅ Local Worker (processa localmente)

---

## 📋 PREPARAÇÃO

### **1. Configurar modo AUTO**

Edite `config/config.yaml`:
```yaml
mode: "AUTO"  # Deve estar em AUTO, não FORCED_OFFLINE
```

### **2. Limpar banco**
```bash
python -c "import sqlite3; conn = sqlite3.connect('./db/miqa.db'); cursor = conn.cursor(); cursor.execute('DELETE FROM queue_items'); cursor.execute('DELETE FROM metrics_events'); conn.commit(); print('✅ Banco limpo'); conn.close()"
```

### **3. Garantir estado ONLINE**
```bash
python -c "from db.repository import QueueRepository; repo = QueueRepository('./db/miqa.db'); repo.set_system_state('connectivity_state', 'ONLINE'); print('✅ Estado: ONLINE')"
```

### **4. Preparar 10 imagens de teste**

**Opção A: Usar stress_test.py**
```bash
# Vai criar 10 imagens únicas
python -c "
import shutil
from pathlib import Path

source = Path('watch/mri/Te-piTr_0001.jpg')
for i in range(10):
    dest = Path(f'watch/mri/failover_test_{i:02d}.jpg')
    shutil.copy2(source, dest)
    # Adicionar bytes únicos
    with open(dest, 'ab') as f:
        f.write(f'\n# Failover test {i}\n'.encode('utf-8'))
print('✅ 10 imagens criadas')
"
```

**Opção B: Copiar manualmente**
```bash
# Copiar 10 imagens MRI reais para watch/mri/
```

---

## 🚀 EXECUÇÃO DO TESTE

### **FASE 1: Iniciar Workers (ONLINE)**

```bash
# Terminal 1: File Listener
python main.py listener

# Terminal 2: Connectivity Manager
python main.py connectivity-manager

# Terminal 3: Cloud Worker
python main.py cloud-worker

# Terminal 4: Local Worker
python main.py local-worker

# Terminal 5: Monitorar status
watch -n 2 "python main.py status"
```

### **FASE 2: Copiar Imagens**

```bash
# Copiar as 10 imagens para watch/mri/
# OU rodar o script acima
```

**Aguarde 5-10 segundos** para File Listener detectar.

### **FASE 3: Verificar Processamento Cloud**

```bash
python main.py status
```

**Esperado:**
```
🌐 Conectividade: ONLINE

📋 Fila:
  Total de itens: 10
  Pendente cloud: 5-8  ← Processando na nuvem
  Pendente local: 10   ← Aguardando (não processa ainda)
  Processados: 2-5     ← Alguns já foram para cloud
```

### **FASE 4: DESLIGAR INTERNET** 🔴

**Quando ver 3-5 imagens processadas na cloud:**

1. **Desligar WiFi** ou **Desconectar cabo de rede**
2. **Aguardar 10-15 segundos** (Connectivity Manager detectar)

### **FASE 5: Verificar Failover**

```bash
python main.py status
```

**Esperado:**
```
🌐 Conectividade: OFFLINE  ← Mudou!

📋 Fila:
  Total de itens: 10
  Pendente cloud: 0      ← Cloud parou
  Pendente local: 5-7    ← Local assumiu!
  Processados: 10        ← Eventualmente todas
```

**Logs esperados:**
```
[INFO] Connectivity Manager: Estado mudou: ONLINE → OFFLINE
[INFO] Cloud Worker: Sistema OFFLINE, aguardando...
[INFO] Local Worker: 🔬 Processando localmente: abc123...
```

### **FASE 6: Aguardar Conclusão**

Aguarde até todas as 10 imagens serem processadas.

### **FASE 7: Verificar Resultados**

```bash
# Ver resultados cloud (processadas antes de desligar)
ls -lh results/online/

# Ver resultados local (processadas após desligar)
ls -lh results/offline/

# Contar
echo "Cloud: $(ls results/online/*.json 2>/dev/null | wc -l)"
echo "Local: $(ls results/offline/*.json 2>/dev/null | wc -l)"
```

**Esperado:**
- `results/online/`: 3-5 arquivos (processadas antes)
- `results/offline/`: 5-7 arquivos (processadas depois)
- **Total: 10 arquivos**

---

## 📊 VALIDAÇÃO DE SUCESSO

### **✅ Teste PASSOU se:**

1. ✅ Connectivity Manager detectou perda de internet (ONLINE → OFFLINE)
2. ✅ Cloud Worker parou de processar
3. ✅ Local Worker assumiu automaticamente
4. ✅ Todas as 10 imagens foram processadas
5. ✅ Resultados divididos entre `online/` e `offline/`
6. ✅ Nenhuma imagem foi perdida

### **❌ Teste FALHOU se:**

1. ❌ Connectivity Manager não detectou (ainda ONLINE)
2. ❌ Local Worker não assumiu (pendente local = 0)
3. ❌ Imagens ficaram travadas (pendente > 0 por >5min)
4. ❌ Total processado < 10

---

## 🔍 MONITORAMENTO EM TEMPO REAL

### **Script de Monitoramento:**

```bash
# Terminal 6: Monitor contínuo
while true; do
  clear
  echo "=== FAILOVER TEST MONITOR ==="
  echo ""
  python main.py status
  echo ""
  echo "Resultados:"
  echo "  Cloud:  $(ls results/online/*.json 2>/dev/null | wc -l) arquivos"
  echo "  Local:  $(ls results/offline/*.json 2>/dev/null | wc -l) arquivos"
  echo "  Total:  $(($(ls results/online/*.json 2>/dev/null | wc -l) + $(ls results/offline/*.json 2>/dev/null | wc -l)))"
  echo ""
  echo "Pressione Ctrl+C para parar"
  sleep 2
done
```

---

## 🐛 TROUBLESHOOTING

### **Problema 1: Connectivity Manager não detecta perda de internet**

**Sintoma:** Ainda mostra ONLINE após desligar

**Solução:**
```bash
# Forçar manualmente
python -c "from db.repository import QueueRepository; repo = QueueRepository('./db/miqa.db'); repo.set_system_state('connectivity_state', 'OFFLINE'); print('✅ Forçado: OFFLINE')"
```

### **Problema 2: Local Worker não assume**

**Sintoma:** Pendente local = 0 mesmo OFFLINE

**Causa:** Local Worker só processa se:
- Sistema está OFFLINE **OU**
- Cloud falhou 3x

**Solução:** Aguardar mais tempo (cloud vai falhar 3x e local assume)

### **Problema 3: Imagens ficam travadas**

**Sintoma:** Pendente > 0 por muito tempo

**Solução:**
```bash
# Ver itens travados
python -c "
import sqlite3
conn = sqlite3.connect('./db/miqa.db')
cursor = conn.cursor()
cursor.execute('''
    SELECT 
        substr(item_uid, 1, 12) as uid,
        cloud_status,
        local_status,
        retry_count
    FROM queue_items
    WHERE (cloud_status IN ('PENDING', 'UPLOADING'))
       OR (local_status IN ('PENDING', 'PROCESSING'))
''')
print('Itens travados:')
for row in cursor.fetchall():
    print(f'  {row[0]}: cloud={row[1]}, local={row[2]}, retries={row[3]}')
conn.close()
"

# Desbloquear
python -c "
import sqlite3
conn = sqlite3.connect('./db/miqa.db')
cursor = conn.cursor()
cursor.execute('''
    UPDATE queue_items 
    SET locked_until = datetime('now')
    WHERE cloud_status = 'UPLOADING' OR local_status = 'PROCESSING'
''')
conn.commit()
print(f'✅ {cursor.rowcount} itens desbloqueados')
conn.close()
"
```

---

## 📝 CHECKLIST DO TESTE

### **Antes:**
- [ ] Modo AUTO configurado
- [ ] Banco limpo
- [ ] Estado ONLINE
- [ ] 10 imagens preparadas
- [ ] 4 workers rodando

### **Durante:**
- [ ] Imagens detectadas (10/10)
- [ ] Cloud começou a processar
- [ ] Internet desligada
- [ ] Connectivity mudou para OFFLINE
- [ ] Local assumiu processamento

### **Depois:**
- [ ] Todas 10 processadas
- [ ] Resultados em online/ e offline/
- [ ] Nenhuma perdida
- [ ] Logs sem erros críticos

---

## 🎯 RESULTADO ESPERADO

```
📊 TESTE DE FAILOVER - RESULTADO

Imagens totais: 10
Processadas na cloud (antes): 4
Processadas localmente (depois): 6
Total processado: 10 ✅

Tempo total: ~2-3 minutos
Tempo de detecção de falha: ~10-15 segundos
Tempo de failover: <5 segundos

Status: ✅ SUCESSO
```

---

## 🔄 FASE BÔNUS: Reconectar Internet

### **Teste de Recovery:**

1. **Religar internet**
2. **Aguardar 30s** (Connectivity detectar)
3. **Verificar estado:** Deve voltar para ONLINE
4. **Copiar mais 5 imagens**
5. **Verificar:** Deve processar na cloud novamente

**Esperado:**
- Sistema volta para ONLINE
- Cloud Worker volta a funcionar
- Novas imagens vão para cloud

---

**Última atualização:** 2026-01-09 17:30
