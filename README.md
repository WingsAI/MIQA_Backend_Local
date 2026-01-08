# Backend Local MIQA

Sistema edge para processamento de imagens médicas com fallback offline.

## 🎯 Objetivo

Processar imagens médicas localmente quando não há conectividade com a nuvem, garantindo que o hospital continue operando mesmo com internet instável.

## 📁 Estrutura

```
Backend_local/
├── edge/                    # Detecção e ingestão de imagens
├── cloud_client/            # Cliente HTTP para nuvem
├── local_processing/        # Processamento offline
├── metrics/                 # Sistema de métricas
├── db/                      # SQLite e migrations
├── connectivity/            # Gerenciamento de conectividade
├── config/                  # Arquivos de configuração
├── utils/                   # Utilitários
├── tests/                   # Testes
├── docs/                    # Documentação
├── main.py                  # CLI principal
└── requirements.txt         # Dependências
```

## 🚀 Quick Start

### 1. Instalar Dependências

```bash
pip install -r requirements.txt
```

### 2. Inicializar Banco de Dados

```bash
python main.py init-db
```

### 3. Configurar

Edite `config/config.yaml` conforme necessário.

### 4. Iniciar Serviços

Em terminais separados:

```bash
# Terminal 1: Listener de arquivos
python main.py listener

# Terminal 2: Gerenciador de conectividade
python main.py connectivity-manager

# Terminal 3: Worker de nuvem
python main.py cloud-worker

# Terminal 4: Worker local
python main.py local-worker
```

## 📖 Comandos Disponíveis

```bash
# Ver todos os comandos
python main.py --help

# Inicializar banco de dados
python main.py init-db

# Monitorar pasta
python main.py listener

# Gerenciar conectividade
python main.py connectivity-manager

# Worker de nuvem
python main.py cloud-worker

# Worker local
python main.py local-worker

# Ver status
python main.py status
```

## 🔧 Configuração

Edite `config/config.yaml`:

- `device_id`: Identificador único do dispositivo
- `mode`: `AUTO` ou `FORCED_OFFLINE`
- `directories.watch`: Pasta monitorada
- `cloud.api_url`: URL da API de produção

## 📊 Status do Projeto

Ver `docs/status.MD` para progresso detalhado.

## 📝 Documentação

- `docs/PRINCIPAL_DOC.md` - Especificação completa
- `docs/todo.md` - Lista de tarefas
- `docs/status.MD` - Status do projeto
- `docs/instructions.md` - Instruções de implementação

## 🏥 Uso em Hospital

1. Configurar `device_id` único para cada dispositivo
2. Apontar `cloud.api_url` para API de produção
3. Iniciar todos os serviços
4. Copiar imagens para pasta `watch/`
5. Sistema processa automaticamente

## 🔄 Fluxo de Processamento

```
Imagem detectada → Fila SQLite → Verificar conectividade
                                        ↓
                        ┌───────────────┴───────────────┐
                        ↓                               ↓
                    ONLINE                          OFFLINE
                        ↓                               ↓
                Enviar para nuvem              Processar localmente
                        ↓                               ↓
                Resultado da API              Salvar em results/
```

## 🛠️ Desenvolvimento

### Tarefa Atual

✅ Tarefa 1: Bootstrap (Completo)
🔴 Tarefa 2: SQLite (Próximo)

### Próximos Passos

1. Implementar Tarefa 2 (SQLite)
2. Implementar Tarefa 3 (Ingestão)
3. Implementar Tarefa 4 (Arquivo Parcial)
4. Implementar Tarefa 5 (Connectivity)
5. Implementar Tarefa 6 (Cloud Worker)
6. Implementar Tarefa 7 (Local Worker)
7. Implementar Tarefa 8 (Métricas)

## 📄 Licença

Propriedade de WingsAI - Uso interno

---

**Versão:** 1.0.0  
**Última atualização:** 2026-01-08
