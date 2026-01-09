# 🏥 GUIA DE USO - Backend Local MIQA

## 🎯 Sistema Pronto para Produção!

Todos os workers estão rodando e o sistema está **ONLINE** ✅

---

## 📁 Como Processar Imagens Reais

### **Passo 1: Copiar Imagens MRI para a Pasta Watch**

```bash
# Copiar uma imagem
cp /caminho/para/sua/imagem_mri.jpg watch/

# Ou copiar várias
cp /caminho/para/pasta_mri/*.jpg watch/

# Ou copiar DICOM
cp /caminho/para/imagem.dcm watch/
```

### **Passo 2: Aguardar Processamento Automático**

O sistema detecta automaticamente e:
1. **File Listener** detecta a imagem
2. **Connectivity Manager** verifica se está online
3. **Cloud Worker** envia para API (se ONLINE)
4. **Local Worker** processa localmente (se OFFLINE)

### **Passo 3: Ver Status**

```bash
python main.py status
```

**Resultado esperado:**
```
📊 Status do Sistema
🌐 Conectividade: ONLINE

📋 Fila:
  Total de itens: 5
  Pendente cloud: 2
  Pendente local: 0
  Processados: 3
  Falhas: 0
```

---

## 🔍 Monitorando em Tempo Real

### **Ver Logs em Tempo Real**

```bash
# Ver todos os logs
tail -f logs/miqa.log

# Ver apenas uploads
tail -f logs/miqa.log | grep "Upload"

# Ver apenas processamento local
tail -f logs/miqa.log | grep "Processamento local"
```

### **Ver Fila no Banco**

```bash
python -c "
import sqlite3
conn = sqlite3.connect('./db/miqa.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT 
        substr(item_uid, 1, 12) as uid,
        substr(path, -30) as arquivo,
        cloud_status,
        local_status
    FROM queue_items
    ORDER BY detected_at DESC
    LIMIT 10
''')

print('Últimos 10 itens:')
print(f'{\"UID\":<15} {\"Arquivo\":<32} {\"Cloud\":<12} {\"Local\":<12}')
print('-' * 75)
for row in cursor.fetchall():
    print(f'{row[0]:<15} {row[1]:<32} {row[2]:<12} {row[3]:<12}')

conn.close()
"
```

---

## 📊 Ver Resultados Processados Localmente

```bash
# Listar resultados
ls -lh results/

# Ver um resultado específico
cat results/abc123...json

# Ver último resultado
cat $(ls -t results/*.json | head -1)
```

**Formato do resultado:**
```json
{
  "score": 85.5,
  "features": {
    "snr_dietrich": 10.4,
    "efc": 0.94,
    "ghosting_ratio": 0.03,
    ...
  },
  "modality": "mri",
  "status": "success",
  "item_uid": "abc123...",
  "processed_at": 1234567890,
  "processing_time_seconds": 2.5
}
```

---

## 🎛️ Controles Úteis

### **Parar Todos os Workers**

```bash
# Pressione Ctrl+C em cada terminal
# Ou feche os terminais
```

### **Reiniciar Sistema**

```bash
# Terminal 1
python main.py listener

# Terminal 2
python main.py connectivity-manager

# Terminal 3
python main.py cloud-worker

# Terminal 4
python main.py local-worker
```

### **Forçar Modo Offline**

Edite `config/config.yaml`:
```yaml
mode: "FORCED_OFFLINE"  # Mude de AUTO para FORCED_OFFLINE
```

Depois reinicie os workers.

### **Limpar Fila (se necessário)**

```bash
python -c "
import sqlite3
conn = sqlite3.connect('./db/miqa.db')
cursor = conn.cursor()

# Deletar apenas itens falhados
cursor.execute('DELETE FROM queue_items WHERE cloud_status=\"FAILED\" OR local_status=\"FAILED\"')

# Ou deletar tudo
# cursor.execute('DELETE FROM queue_items')

conn.commit()
print(f'✅ {cursor.rowcount} itens deletados')
conn.close()
"
```

---

## 🐛 Troubleshooting

### **Problema: Imagem não é detectada**

**Causa:** Extensão não suportada ou arquivo muito grande

**Solução:**
- Extensões suportadas: `.jpg`, `.jpeg`, `.png`, `.dcm`
- Verifique logs: `tail -f logs/miqa.log | grep "Arquivo detectado"`

### **Problema: Upload falha com HTTP 500**

**Causa:** API de produção com erro ou imagem inválida

**Solução:**
- Verifique se imagem é válida
- Sistema fará retry automático (3 tentativas)
- Se continuar falhando, será processado localmente

### **Problema: Sistema sempre OFFLINE**

**Causa:** API não acessível ou configuração errada

**Solução:**
```bash
# Testar healthcheck manualmente
curl https://miqaback-production.up.railway.app/health

# Ver logs do connectivity manager
tail -f logs/miqa.log | grep "Healthcheck"
```

### **Problema: Processamento local muito lento**

**Causa:** Imagens muito grandes ou CPU fraco

**Solução:**
- Reduzir `max_concurrent_processing` em `config.yaml`
- Usar imagens menores
- Considerar GPU (futuro)

---

## 📈 Métricas

### **Ver Métricas Coletadas**

```bash
python -c "
from metrics.collector import MetricsCollector

collector = MetricsCollector('hospital-device-001')
summary = collector.get_metrics_summary(since_minutes=60)

print(f'Total de eventos: {summary[\"total_events\"]}')
print('\nMétricas (últimos 60 min):')
for name, stats in summary['metrics'].items():
    print(f'  {name}:')
    print(f'    Count: {stats[\"count\"]}')
    print(f'    Avg: {stats[\"avg\"]}')
    print(f'    Min: {stats[\"min\"]}')
    print(f'    Max: {stats[\"max\"]}')
"
```

---

## 🎯 Exemplo Completo: Processar 10 Imagens MRI

```bash
# 1. Copiar imagens
cp /caminho/para/mri/*.jpg watch/

# 2. Ver status
python main.py status

# 3. Aguardar processamento (ver logs)
tail -f logs/miqa.log

# 4. Ver resultados
ls -lh results/

# 5. Ver estatísticas
python -c "
import sqlite3
conn = sqlite3.connect('./db/miqa.db')
cursor = conn.cursor()

cursor.execute('SELECT cloud_status, COUNT(*) FROM queue_items GROUP BY cloud_status')
print('Status Cloud:')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]}')

cursor.execute('SELECT local_status, COUNT(*) FROM queue_items GROUP BY local_status')
print('\nStatus Local:')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]}')

conn.close()
"
```

---

## ✅ Checklist Antes de Usar em Produção

- [x] Todos os workers rodando
- [x] Sistema ONLINE
- [x] Banco limpo (sem itens de teste)
- [ ] Configurar `device_id` único em `config.yaml`
- [ ] Testar com 1 imagem real
- [ ] Testar com 10 imagens reais
- [ ] Testar modo offline (desligar internet)
- [ ] Verificar logs estruturados
- [ ] Verificar métricas

---

## 🚀 Pronto para Usar!

Agora é só copiar suas imagens MRI reais para a pasta `watch/` e o sistema fará o resto automaticamente!

**Boa sorte!** 🎉

---

**Última atualização:** 2026-01-09 10:05
