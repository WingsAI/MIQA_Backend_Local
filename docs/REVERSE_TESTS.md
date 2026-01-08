# 🧪 TESTES REVERSOS - Tarefas 3 e 4

## 🎯 Objetivo

Testar cenários de falha, edge cases e comportamentos inesperados para garantir robustez do sistema.

---

## 📁 Tarefa 3: Ingestão - TESTES REVERSOS

### 🔴 Teste 1: Arquivo com Extensão Inválida

**Objetivo:** Verificar se ignora arquivos não suportados

```bash
# Criar arquivo .txt
echo "teste" > watch/arquivo.txt

# Criar arquivo .pdf
echo "fake pdf" > watch/documento.pdf

# Aguardar 5 segundos
sleep 5

# Verificar banco - NÃO deve ter registrado
python -c "
from db.repository import QueueRepository
repo = QueueRepository('./db/miqa.db')
items = repo.get_pending_cloud()
txt_items = [i for i in items if 'arquivo.txt' in i['path']]
pdf_items = [i for i in items if 'documento.pdf' in i['path']]
print(f'Arquivos .txt registrados: {len(txt_items)}')  # Deve ser 0
print(f'Arquivos .pdf registrados: {len(pdf_items)}')  # Deve ser 0
"
```

**Resultado Esperado:**
```
Arquivos .txt registrados: 0
Arquivos .pdf registrados: 0
```

**Status:** ⏳ PENDENTE

---

### 🔴 Teste 2: Arquivo Vazio

**Objetivo:** Verificar comportamento com arquivo de 0 bytes

```bash
# Criar arquivo vazio
touch watch/vazio.jpg

# Aguardar processar
sleep 5

# Verificar se foi registrado
python -c "
from db.repository import QueueRepository
repo = QueueRepository('./db/miqa.db')
items = repo.get_pending_cloud()
empty_items = [i for i in items if 'vazio.jpg' in i['path']]
print(f'Arquivos vazios: {len(empty_items)}')
if empty_items:
    print(f'UID: {empty_items[0][\"item_uid\"]}')
"
```

**Resultado Esperado:**
- Arquivo deve ser registrado (UID será hash de arquivo vazio)
- UID deve ser consistente: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

**Status:** ⏳ PENDENTE

---

### 🔴 Teste 3: Arquivo Duplicado (Mesmo Conteúdo)

**Objetivo:** Verificar idempotência - mesmo arquivo não deve duplicar

```bash
# Criar arquivo
echo "conteudo teste" > watch/original.jpg

# Aguardar processar
sleep 5

# Criar cópia com nome diferente mas mesmo conteúdo
cp watch/original.jpg watch/copia.jpg

# Aguardar processar
sleep 5

# Verificar UIDs
python -c "
from db.repository import QueueRepository
import sqlite3

conn = sqlite3.connect('./db/miqa.db')
cursor = conn.cursor()

cursor.execute('SELECT item_uid, path FROM queue_items WHERE path LIKE \"%original.jpg%\" OR path LIKE \"%copia.jpg%\"')
items = cursor.fetchall()

print(f'Total de registros: {len(items)}')
for uid, path in items:
    print(f'  {uid[:16]}... - {path}')

# Verificar se UIDs são iguais
if len(items) == 2:
    uid1, uid2 = items[0][0], items[1][0]
    print(f'UIDs iguais: {uid1 == uid2}')  # Deve ser True

conn.close()
"
```

**Resultado Esperado:**
- 2 registros no banco (paths diferentes)
- UIDs **iguais** (mesmo conteúdo)
- Segundo insert deve fazer UPDATE (upsert)

**Status:** ⏳ PENDENTE

---

### 🔴 Teste 4: Arquivo Muito Grande

**Objetivo:** Verificar se processa arquivos grandes sem travar

```bash
# Criar arquivo de 100MB
python -c "
import numpy as np
from PIL import Image

# Criar imagem grande (10000x10000 pixels)
img = Image.fromarray(np.random.randint(0, 255, (10000, 10000, 3), dtype=np.uint8))
img.save('watch/grande.jpg', quality=95)
print('Arquivo grande criado')
"

# Monitorar tempo de processamento
time python -c "
from edge.listener import ImageFileHandler
from db.repository import QueueRepository
from pathlib import Path
import yaml

config = yaml.safe_load(open('config/config.yaml'))
repo = QueueRepository(config['database']['path'])
handler = ImageFileHandler(repo, config)

import time
start = time.time()
handler._handle_file(Path('watch/grande.jpg'))
duration = time.time() - start

print(f'Tempo de processamento: {duration:.2f}s')
"
```

**Resultado Esperado:**
- Deve processar sem erro
- Tempo < 30 segundos
- UID gerado corretamente

**Status:** ⏳ PENDENTE

---

### 🔴 Teste 5: Arquivo com Nome Especial

**Objetivo:** Verificar se lida com caracteres especiais no nome

```bash
# Criar arquivos com nomes especiais
touch "watch/arquivo com espaços.jpg"
touch "watch/arquivo_com_acentuação_çãõ.jpg"
touch "watch/arquivo-com-hífen.jpg"
touch "watch/arquivo.múltiplos.pontos.jpg"

# Processar
python -c "
from edge.listener import ImageFileHandler
from db.repository import QueueRepository
from pathlib import Path
import yaml

config = yaml.safe_load(open('config/config.yaml'))
repo = QueueRepository(config['database']['path'])
handler = ImageFileHandler(repo, config)

test_files = [
    'watch/arquivo com espaços.jpg',
    'watch/arquivo_com_acentuação_çãõ.jpg',
    'watch/arquivo-com-hífen.jpg',
    'watch/arquivo.múltiplos.pontos.jpg'
]

for f in test_files:
    try:
        handler._handle_file(Path(f))
        print(f'✅ {f}')
    except Exception as e:
        print(f'❌ {f}: {e}')
"
```

**Resultado Esperado:**
- Todos devem processar sem erro
- Paths salvos corretamente no banco

**Status:** ⏳ PENDENTE

---

### 🔴 Teste 6: Pasta Monitorada Não Existe

**Objetivo:** Verificar se cria pasta automaticamente

```bash
# Remover pasta watch
rm -rf watch

# Tentar iniciar listener
python -c "
from edge.listener import FileListener
import yaml

config = yaml.safe_load(open('config/config.yaml'))
listener = FileListener(config)
print('Listener criado com sucesso')

# Verificar se pasta foi criada
from pathlib import Path
if Path('watch').exists():
    print('✅ Pasta watch criada automaticamente')
else:
    print('❌ Pasta watch NÃO foi criada')
"
```

**Resultado Esperado:**
```
Listener criado com sucesso
✅ Pasta watch criada automaticamente
```

**Status:** ⏳ PENDENTE

---

### 🔴 Teste 7: Arquivo Deletado Durante Processamento

**Objetivo:** Verificar se lida com arquivo que desaparece

```bash
# Criar arquivo
echo "teste" > watch/temporario.jpg

# Processar em background e deletar imediatamente
python -c "
from edge.listener import ImageFileHandler
from db.repository import QueueRepository
from pathlib import Path
import yaml
import os
import threading
import time

config = yaml.safe_load(open('config/config.yaml'))
repo = QueueRepository(config['database']['path'])
handler = ImageFileHandler(repo, config)

test_file = Path('watch/temporario.jpg')

# Deletar após 0.1s
def delete_file():
    time.sleep(0.1)
    if test_file.exists():
        os.remove(test_file)
        print('Arquivo deletado')

thread = threading.Thread(target=delete_file)
thread.start()

# Tentar processar
try:
    handler._handle_file(test_file)
    print('✅ Processou sem erro')
except Exception as e:
    print(f'❌ Erro: {e}')

thread.join()
"
```

**Resultado Esperado:**
- Deve lidar gracefully com erro
- Não deve crashar
- Log de warning

**Status:** ⏳ PENDENTE

---

### 🔴 Teste 8: Permissão Negada

**Objetivo:** Verificar se lida com arquivo sem permissão de leitura

```bash
# Criar arquivo
echo "teste" > watch/sem_permissao.jpg

# Remover permissão de leitura (Linux/Mac)
chmod 000 watch/sem_permissao.jpg

# Tentar processar
python -c "
from edge.listener import ImageFileHandler
from db.repository import QueueRepository
from pathlib import Path
import yaml

config = yaml.safe_load(open('config/config.yaml'))
repo = QueueRepository(config['database']['path'])
handler = ImageFileHandler(repo, config)

try:
    handler._handle_file(Path('watch/sem_permissao.jpg'))
    print('✅ Processou sem erro')
except PermissionError:
    print('❌ PermissionError capturado corretamente')
except Exception as e:
    print(f'❌ Outro erro: {e}')
"

# Restaurar permissão
chmod 644 watch/sem_permissao.jpg
```

**Resultado Esperado:**
```
❌ PermissionError capturado corretamente
```

**Status:** ⏳ PENDENTE (Windows não suporta chmod)

---

## 🛡️ Tarefa 4: Arquivo Parcial - TESTES REVERSOS

### 🔴 Teste 9: Arquivo Sendo Escrito Lentamente

**Objetivo:** Verificar se detecta arquivo instável

```python
# Simular escrita lenta
python -c "
import time
from pathlib import Path

# Criar arquivo e escrever aos poucos
test_file = Path('watch/escrita_lenta.jpg')

with open(test_file, 'wb') as f:
    for i in range(10):
        f.write(b'x' * 1000)
        f.flush()
        print(f'Escrito {(i+1)*1000} bytes')
        time.sleep(0.5)  # Pausa entre escritas

print('Escrita concluída')
"

# Em outro terminal, tentar verificar estabilidade
python -c "
from utils.file_stability import is_file_stable
from pathlib import Path

stable = is_file_stable(Path('watch/escrita_lenta.jpg'), checks=3, interval=0.5)
print(f'Arquivo estável: {stable}')  # Deve ser False durante escrita
"
```

**Resultado Esperado:**
- Durante escrita: `False`
- Após escrita: `True`

**Status:** ⏳ PENDENTE

---

### 🔴 Teste 10: Arquivo que Nunca Estabiliza

**Objetivo:** Verificar timeout

```python
# Simular arquivo que nunca estabiliza
python -c "
import time
from pathlib import Path
import threading

test_file = Path('watch/nunca_estabiliza.jpg')

# Thread que continua modificando arquivo
def keep_modifying():
    for i in range(100):
        with open(test_file, 'ab') as f:
            f.write(b'x')
        time.sleep(0.5)

thread = threading.Thread(target=keep_modifying)
thread.start()

# Tentar verificar estabilidade com timeout curto
from utils.file_stability import is_file_stable
import time

time.sleep(1)  # Aguardar arquivo ser criado

start = time.time()
stable = is_file_stable(test_file, checks=5, interval=0.5, timeout=5)
duration = time.time() - start

print(f'Estável: {stable}')  # Deve ser False
print(f'Tempo: {duration:.2f}s')  # Deve ser ~5s (timeout)

thread.join()
"
```

**Resultado Esperado:**
```
Estável: False
Tempo: ~5.0s
```

**Status:** ⏳ PENDENTE

---

### 🔴 Teste 11: Arquivo Modificado Após Estabilizar

**Objetivo:** Verificar se detecta modificação posterior

```bash
# Criar arquivo
echo "versao 1" > watch/modificado.jpg

# Aguardar estabilizar e processar
sleep 10

# Modificar arquivo
echo "versao 2" >> watch/modificado.jpg

# Aguardar processar novamente
sleep 10

# Verificar se gerou UID diferente
python -c "
import sqlite3

conn = sqlite3.connect('./db/miqa.db')
cursor = conn.cursor()

cursor.execute('SELECT item_uid FROM queue_items WHERE path LIKE \"%modificado.jpg%\"')
uids = [row[0] for row in cursor.fetchall()]

print(f'Total de UIDs: {len(uids)}')
print(f'UIDs únicos: {len(set(uids))}')

if len(set(uids)) > 1:
    print('✅ UIDs diferentes (arquivo modificado detectado)')
else:
    print('⚠️  Mesmo UID (pode ser esperado se fez upsert)')

conn.close()
"
```

**Resultado Esperado:**
- Deve detectar modificação
- Pode gerar novo UID ou fazer upsert (depende da implementação)

**Status:** ⏳ PENDENTE

---

### 🔴 Teste 12: Múltiplos Arquivos Simultâneos

**Objetivo:** Verificar se processa múltiplos arquivos em paralelo

```bash
# Criar 10 arquivos simultaneamente
for i in {1..10}; do
    echo "arquivo $i" > "watch/batch_$i.jpg" &
done
wait

# Aguardar processar
sleep 10

# Verificar quantos foram registrados
python -c "
import sqlite3

conn = sqlite3.connect('./db/miqa.db')
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM queue_items WHERE path LIKE \"%batch_%\"')
count = cursor.fetchone()[0]

print(f'Arquivos batch registrados: {count}')  # Deve ser 10

conn.close()
"
```

**Resultado Esperado:**
```
Arquivos batch registrados: 10
```

**Status:** ⏳ PENDENTE

---

### 🔴 Teste 13: Arquivo Movido Durante Verificação

**Objetivo:** Verificar se lida com arquivo que é movido

```bash
# Criar arquivo
echo "teste" > watch/sera_movido.jpg

# Mover arquivo durante processamento
python -c "
from utils.file_stability import is_file_stable
from pathlib import Path
import threading
import time
import shutil

test_file = Path('watch/sera_movido.jpg')

# Mover após 1s
def move_file():
    time.sleep(1)
    shutil.move(str(test_file), 'watch/movido.jpg')
    print('Arquivo movido')

thread = threading.Thread(target=move_file)
thread.start()

# Tentar verificar estabilidade
try:
    stable = is_file_stable(test_file, checks=5, interval=0.5, timeout=10)
    print(f'Estável: {stable}')
except Exception as e:
    print(f'Erro: {e}')

thread.join()
"
```

**Resultado Esperado:**
- Deve retornar `False` (arquivo desapareceu)
- Ou capturar `FileNotFoundError`

**Status:** ⏳ PENDENTE

---

## 📊 Resumo dos Testes Reversos

| # | Teste | Categoria | Criticidade | Status |
|---|-------|-----------|-------------|--------|
| 1 | Extensão inválida | Validação | Média | ⏳ |
| 2 | Arquivo vazio | Edge case | Baixa | ⏳ |
| 3 | Arquivo duplicado | Idempotência | Alta | ⏳ |
| 4 | Arquivo grande | Performance | Alta | ⏳ |
| 5 | Nome especial | Encoding | Média | ⏳ |
| 6 | Pasta não existe | Inicialização | Alta | ⏳ |
| 7 | Arquivo deletado | Concorrência | Alta | ⏳ |
| 8 | Sem permissão | Segurança | Média | ⏳ |
| 9 | Escrita lenta | Estabilidade | Alta | ⏳ |
| 10 | Nunca estabiliza | Timeout | Alta | ⏳ |
| 11 | Modificado depois | Versionamento | Média | ⏳ |
| 12 | Múltiplos simultâneos | Concorrência | Alta | ⏳ |
| 13 | Movido durante check | Race condition | Alta | ⏳ |

---

## 🎯 Como Executar

### Executar Todos os Testes

```bash
# Criar script de teste
cat > test_reverse.sh << 'EOF'
#!/bin/bash
echo "🧪 Executando testes reversos..."

# Teste 1: Extensão inválida
echo "teste" > watch/arquivo.txt
sleep 2

# Teste 2: Arquivo vazio
touch watch/vazio.jpg
sleep 2

# ... adicionar outros testes

echo "✅ Testes concluídos"
EOF

chmod +x test_reverse.sh
./test_reverse.sh
```

### Executar Teste Individual

```bash
# Exemplo: Teste 3 (duplicado)
echo "conteudo teste" > watch/original.jpg
sleep 5
cp watch/original.jpg watch/copia.jpg
sleep 5
python main.py status
```

---

**Última atualização:** 2026-01-08 16:20
