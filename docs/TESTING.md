# Testes - Backend Local MIQA

## Quick Tests

### Verificar Sistema
```bash
python main.py status
```

### Teste Completo Online
```bash
# Iniciar serviços (4 terminais)
python main.py listener
python main.py connectivity-manager
python main.py cloud-worker
python main.py local-worker

# Copiar imagem
cp test.jpg watch/mri/

# Verificar resultado
python main.py status
```

### Teste Offline
```bash
# Editar config/config.yaml: mode: "FORCED_OFFLINE"
# Copiar imagem
cp test.jpg watch/mri/

# Resultado salvo em results/offline/
```

---

## Stress Test

```bash
# 100 imagens (padrão)
python stress_test.py

# Quantidade customizada
python stress_test.py 50
python stress_test.py 500
```

**Benchmarks:**
- Cloud: > 30 img/min (bom)
- Local: > 10 img/min (bom)

---

## Teste de Failover

Testar roteamento inteligente: cloud → local quando internet cai.

### Preparação
```bash
# Limpar banco
python -c "import sqlite3; conn = sqlite3.connect('./db/miqa.db'); conn.execute('DELETE FROM queue_items'); conn.commit(); conn.close()"

# Garantir ONLINE
python -c "from db.repository import QueueRepository; repo = QueueRepository('./db/miqa.db'); repo.set_system_state('connectivity_state', 'ONLINE')"
```

### Execução
1. Iniciar 4 workers
2. Copiar 10 imagens para `watch/mri/`
3. Aguardar algumas processarem na cloud
4. **Desligar WiFi/internet**
5. Aguardar sistema detectar OFFLINE (~10s)
6. Local worker assume automaticamente

### Validação
```bash
# Contar resultados
echo "Cloud: $(ls results/online/*.json 2>/dev/null | wc -l)"
echo "Local: $(ls results/offline/*.json 2>/dev/null | wc -l)"
```

---

## Troubleshooting

### Workers não processam
```bash
# Verificar processos
ps aux | grep "main.py"
```

### Imagens travadas
```bash
# Desbloquear
python -c "
import sqlite3
conn = sqlite3.connect('./db/miqa.db')
conn.execute(\"UPDATE queue_items SET locked_until = datetime('now') WHERE cloud_status = 'UPLOADING' OR local_status = 'PROCESSING'\")
conn.commit()
print('Desbloqueado')
"
```

### Forçar estado OFFLINE
```bash
python -c "from db.repository import QueueRepository; repo = QueueRepository('./db/miqa.db'); repo.set_system_state('connectivity_state', 'OFFLINE')"
```

---

## Limpeza

```bash
# Limpar imagens de teste
rm watch/mri/stress_test_*.jpg

# Limpar banco
python -c "import sqlite3; conn = sqlite3.connect('./db/miqa.db'); conn.execute('DELETE FROM queue_items'); conn.commit()"

# Limpar resultados
rm -rf results/online/*.json results/offline/*.json
```
