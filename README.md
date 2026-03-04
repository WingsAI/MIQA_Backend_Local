# MIQA Backend Local

Edge AI system for medical image quality assessment with offline fallback and decentralized storage via Filecoin/IPFS.

Built by [WingsAI](https://wingsai.com.br) — open-source medical AI infrastructure for the Global South.

**License:** MIT + Apache 2.0

---

## 🎯 What It Does

Processes medical images (MRI, CT, Ultrasound) directly on hospital devices:
- Runs AI quality assessment **fully offline** when internet is unavailable
- Syncs results to production API when connectivity returns
- Publishes results to **Filecoin/IPFS** for verifiable, sovereignty-respecting data storage

## 📁 Structure

```
MIQA_Backend_Local/
├── edge/                    # Image detection and ingestion (watchdog)
├── cloud_client/            # HTTP client for production API
├── local_processing/        # Offline AI processing (MRI, CT, US heuristics)
├── filecoin/                # Filecoin/IPFS decentralized storage layer
│   ├── ipfs_client.py       # IPFS upload client (Lighthouse + Web3.Storage)
│   └── worker.py            # FilecoinWorker — publishes results to IPFS
├── metrics/                 # Observability and sync
├── db/                      # SQLite + migrations
│   └── migrations/
│       ├── 001_initial.sql
│       └── 002_filecoin_columns.sql
├── connectivity/            # Connectivity state management
├── config/                  # config.yaml (git-ignored — contains secrets)
├── utils/                   # Logging, file stability
├── docs/                    # Architecture, usage guide, testing
├── .env.example             # Environment variables template
├── main.py                  # CLI entry point
└── requirements.txt
```

## 🚀 Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and add your Lighthouse API key
```

Get a free Lighthouse API key at [lighthouse.storage](https://lighthouse.storage).

### 3. Configure the system

Edit `config/config.yaml`:
- `device_id`: unique identifier for this hospital device
- `mode`: `AUTO` or `FORCED_OFFLINE`
- `cloud.api_url`: production API URL
- `filecoin.enabled`: `true` to activate IPFS publishing

```yaml
filecoin:
  enabled: true
  backend: lighthouse        # or "w3s" for Web3.Storage
  api_key: ""                # set via LIGHTHOUSE_API_KEY env var instead
  worker_interval: 30        # seconds between IPFS publishing cycles
  upload_images: true        # set false to publish only result manifests
```

### 4. Initialize database

```bash
python main.py init-db
# Apply Filecoin migration
sqlite3 db/miqa.db < db/migrations/002_filecoin_columns.sql
```

### 5. Start services

**AUTO mode (with internet):**
```bash
python main.py listener &
python main.py connectivity-manager &
python main.py cloud-worker &
python main.py local-worker &
python main.py sync-worker
```

**FORCED_OFFLINE mode:**
```bash
# Set mode: "FORCED_OFFLINE" in config/config.yaml
python main.py listener &
python main.py connectivity-manager &
python main.py local-worker &
python main.py sync-worker
```

**Stop all:**
```bash
pkill -f "main.py"
```

## 📖 CLI Commands

```bash
python main.py --help              # List all commands
python main.py init-db             # Initialize SQLite database
python main.py listener            # Monitor watch/ directory for new images
python main.py connectivity-manager  # Monitor cloud API health
python main.py cloud-worker        # Upload images to production API (online)
python main.py local-worker        # Process images locally (offline)
python main.py sync-worker         # Sync offline results to API when reconnected
python main.py status              # Show system status
```

## 🔄 Processing Flow

```
Image detected → SHA256 uid → SQLite queue → Check connectivity
                                                      ↓
                                     ┌────────────────┴────────────────┐
                                     ↓                                 ↓
                                  ONLINE                           OFFLINE
                                     ↓                                 ↓
                             Cloud Worker                       Local Worker
                             (API upload)                   (local AI model)
                                     ↓                                 ↓
                              results/online/                 results/offline/
                                     └────────────────┬────────────────┘
                                                      ↓
                                             FilecoinWorker
                                      (publishes to IPFS/Filecoin)
                                                      ↓
                                    image CID + manifest CID → results/ipfs/
```

## 🌐 Filecoin/IPFS Integration

Every processed image and its AI result is published to Filecoin via IPFS:

- **Image CID**: immutable content address of the original medical image
- **Manifest CID**: JSON linking the image CID + MIQA quality score + metadata

This gives hospitals:
- **Data sovereignty**: results stored on a decentralized network, not a single vendor
- **Auditability**: any regulator can verify results using the CID (cryptographic proof)
- **Reproducibility**: results are independently verifiable by other institutions

Results are saved locally at `results/ipfs/<item_uid>.json`:
```json
{
  "item_uid": "sha256...",
  "image_cid": "bafy2bzace...",
  "manifest_cid": "bafy2bzace...",
  "image_gateway": "https://gateway.lighthouse.storage/ipfs/bafy...",
  "manifest_gateway": "https://gateway.lighthouse.storage/ipfs/bafy...",
  "published_at": 1741123456.7,
  "miqa_result": { ... }
}
```

## 🏥 Hospital Deployment

1. Set a unique `device_id` for each device
2. Point `cloud.api_url` to the production API
3. Add `LIGHTHOUSE_API_KEY` to `.env`
4. Drop images into `watch/mri/`, `watch/ct/`, or `watch/us/`
5. System processes automatically

## 🛠️ Development Status

| Task | Status |
|------|--------|
| Bootstrap & SQLite | ✅ Done |
| Image ingestion (watchdog) | ✅ Done |
| Partial file detection | ✅ Done |
| Connectivity management | ✅ Done |
| Cloud Worker | ✅ Done |
| Local Worker (MRI/CT/US) | ✅ Done |
| Metrics & observability | ✅ Done |
| **Filecoin/IPFS integration** | ✅ Done (04/03/2026) |
| Metrics export | 🔲 P1 |
| Encryption at rest | 🔲 P2 |
| Automated cleanup | 🔲 P2 |
| Automated tests | 🔲 P1 |

## 📄 Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system architecture
- [docs/GUIA_DE_USO.md](docs/GUIA_DE_USO.md) — operator guide (PT-BR)
- [docs/TESTING.md](docs/TESTING.md) — testing and troubleshooting

## 🤝 Contributing

This project is open-source (MIT + Apache 2.0). Contributions welcome, especially:
- DICOM SCP receiver implementation
- Additional modality heuristics
- IPFS backend integrations

---

**Version:** 1.1.0
**Last updated:** 2026-03-04
