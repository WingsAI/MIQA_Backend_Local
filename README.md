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

**Modo AUTO (com internet):**
```bash
python3 main.py listener & python3 main.py connectivity-manager & python3 main.py cloud-worker & python3 main.py local-worker & python3 main.py sync-worker
```

**Modo FORCED_OFFLINE (sem internet):**
```bash
# Edite config/config.yaml: mode: "FORCED_OFFLINE"
python3 main.py listener & python3 main.py connectivity-manager & python3 main.py local-worker & python3 main.py sync-worker
```

**Parar todos:**
```bash
pkill -f "main.py"
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

## Documentação

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - Arquitetura técnica
- [docs/GUIA_DE_USO.md](docs/GUIA_DE_USO.md) - Guia para operadores
- [docs/TESTING.md](docs/TESTING.md) - Testes e troubleshooting

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

### Status das Tarefas

| Tarefa | Status |
|--------|--------|
| 1. Bootstrap | ✅ Concluído |
| 2. SQLite | ✅ Concluído |
| 3. Ingestão | ✅ Concluído |
| 4. Arquivo Parcial | ✅ Concluído |
| 5. Connectivity | ✅ Concluído |
| 6. Cloud Worker | ✅ Concluído |
| 7. Local Worker | ✅ Concluído |
| 8. Métricas | ✅ Concluído |

**Todas as 8 tarefas críticas foram concluídas.**

### Próximos Passos

1. Tarefa 9: Exportação de métricas (P1)
2. Tarefa 10: Criptografia (P2)
3. Tarefa 11: Limpeza automática (P2)
4. Tarefa 12: Testes automatizados (P1)
5. Deploy no hospital

## 📄 Licença

Propriedade de WingsAI - Uso interno

---

**Versão:** 1.0.0
**Última atualização:** 2026-01-14
