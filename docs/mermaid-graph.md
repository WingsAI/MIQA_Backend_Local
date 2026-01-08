flowchart LR
  subgraph HOSP["Hospital"]
    MOD["Modalidade US RX CT"]
    PACS["PACS ou Backup"]
    SHARE["Pasta de saida"]
    MOD -->|Imagens| PACS
    PACS -->|Exporta| SHARE
  end

  subgraph EDGE["Edge Raspberry Pi"]
    INDEC["Origem das imagens"]
    LISTENER["Listener de pasta"]
    DICOM["Receiver DICOM SCP opcional"]
    PARTIAL["Protecao arquivo parcial\nprocessar so quando arquivo estiver estavel"]

    DB["SQLite queue\nchave unica item uid\nestados cloud e local"]

    CM["Connectivity manager\nmodo AUTO ou FORCED OFFLINE\nhealthcheck latencia erros"]

    CLOUDW["Worker cloud sender\nretry backoff idempotencia"]
    LOCALW["Worker processamento local fallback"]

    MET["Metricas e logs locais"]
    METDEC["Exportar metricas"]
    BATCH["Enviar em lote quando online"]
    KEEP["Guardar local para coleta presencial"]

    INDEC -->|Pasta| LISTENER
    INDEC -->|DICOM| DICOM

    LISTENER --> PARTIAL
    DICOM --> PARTIAL
    PARTIAL -->|Registrar ou atualizar item| DB

    CM --> CLOUDW
    CM --> LOCALW

    DB --> CLOUDW
    DB --> LOCALW

    CLOUDW -->|Atualiza status no DB| DB
    LOCALW -->|Atualiza status no DB| DB

    CLOUDW --> MET
    LOCALW --> MET
    CM --> MET

    MET --> METDEC
    METDEC -->|Se online e permitido| BATCH
    METDEC -->|Se offline| KEEP
  end

  SHARE --> INDEC

  subgraph CLOUD["Nuvem"]
    API["API ingestao e healthcheck"]
    AI["Analise na nuvem\nmetricas e nota 0 a 100"]
    RES["Armazenamento resultados"]
    GW["Gateway metricas ou endpoint eventos"]
    PROM["Prometheus"]
    GRAF["Grafana"]

    API --> AI --> RES
    GW --> PROM --> GRAF
  end

  CLOUDW -->|Enviar via TLS mTLS| API
  BATCH -->|Enviar lote| GW
  CM -->|Healthcheck| API