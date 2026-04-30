"""MIQA API — REST API para processamento de imagens médicas.

Endpoints:
  POST /analyze           → Analisa qualidade de uma imagem
  GET  /health            → Health check
  GET  /models            → Lista modelos disponíveis
  GET  /metrics           → Métricas do sistema

Uso:
    python -m miqa.api

Ou com uvicorn:
    uvicorn miqa.api:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations
import io
import time
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from miqa.ml_models import predict_quality, list_available_models
from miqa.anatomy import detect_anatomy


app = FastAPI(
    title="MIQA API",
    description="Medical Image Quality Assessment — CPU-only lightweight models",
    version="1.1.0",
)

# CORS para o frontend no Railway
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especificar o domínio do frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalysisResponse(BaseModel):
    status: str
    modality: str
    body_part: str
    score: float
    confidence: float
    features: dict
    processing_time_ms: float


class HealthResponse(BaseModel):
    status: str
    version: str
    models_loaded: int
    uptime_seconds: float


# Startup time para uptime
_start_time = time.time()


@app.get("/", tags=["root"])
async def root():
    """Root endpoint."""
    return {
        "service": "MIQA API",
        "version": "1.1.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health():
    """Health check — retorna status e modelos carregados."""
    models = list_available_models()
    total_models = sum(len(bp) for mod in models.values() for bp in mod.values())
    
    return HealthResponse(
        status="healthy",
        version="1.1.0",
        models_loaded=total_models,
        uptime_seconds=round(time.time() - _start_time, 1),
    )


@app.get("/models", tags=["models"])
async def get_models():
    """Lista todos os modelos disponíveis."""
    return list_available_models()


@app.post("/analyze", response_model=AnalysisResponse, tags=["analysis"])
async def analyze(
    file: UploadFile = File(...),
    modality: Optional[str] = None,
    body_part: Optional[str] = None,
):
    """Analisa qualidade de uma imagem médica.
    
    Args:
        file: Imagem (PNG, JPG, DICOM)
        modality: rx, us, ct, mri (opcional — auto-detect se omitido)
        body_part: chest, brain, etc. (opcional — auto-detect se omitido)
    
    Returns:
        Score de qualidade [0, 100] + features + metadata
    """
    t0 = time.time()
    
    # Valida arquivo
    if not file.content_type or not file.content_type.startswith("image/"):
        if not file.filename or not file.filename.lower().endswith((".dcm", ".dicom")):
            raise HTTPException(400, "Arquivo deve ser imagem (PNG, JPG) ou DICOM")
    
    try:
        # Lê imagem
        contents = await file.read()
        img = Image.open(io.BytesIO(contents)).convert("L")
        img_array = np.array(img).astype(np.float32)
        
        # Normaliza
        a, b = float(img_array.min()), float(img_array.max())
        img_norm = (img_array - a) / max(b - a, 1e-9)
        
        # Detecta anatomia se não fornecido
        if not modality or not body_part:
            ctx = detect_anatomy(Path(file.filename), img=img_norm)
            modality = modality or ctx.modality
            body_part = body_part or ctx.body_part.value
        
        # Prediz score
        score = predict_quality(
            Path(file.filename), 
            modality=modality, 
            body_part=body_part
        )
        
        if score is None:
            # Fallback: usa heurísticas físicas
            from miqa.ml_models.train_lightweight import extract_features, compute_teacher_score
            features = extract_features(Path(file.filename), modality)
            score = compute_teacher_score(features)
        
        processing_time = (time.time() - t0) * 1000
        
        return AnalysisResponse(
            status="success",
            modality=modality,
            body_part=body_part,
            score=round(float(score), 2),
            confidence=0.85,  # TODO: calcular confiança real
            features={},  # TODO: retornar features extraídas
            processing_time_ms=round(processing_time, 1),
        )
        
    except Exception as e:
        raise HTTPException(500, f"Erro processando imagem: {str(e)}")


@app.get("/metrics", tags=["metrics"])
async def metrics():
    """Métricas do sistema para observabilidade."""
    models = list_available_models()
    return {
        "uptime_seconds": round(time.time() - _start_time, 1),
        "models_loaded": sum(len(bp) for mod in models.values() for bp in mod.values()),
        "models_by_modality": {
            mod: len(bps) for mod, bps in models.items()
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)