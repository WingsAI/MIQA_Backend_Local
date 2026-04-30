# MIQA Backend API
# Dockerfile para deploy no Railway

FROM python:3.11-slim

WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia código
COPY . .

# Cria diretório para modelos (será montado via Volume no Railway)
RUN mkdir -p /app/miqa/ml_models/checkpoints

# Porta exposta
EXPOSE 8000

# Comando de startup
CMD ["uvicorn", "miqa.api:app", "--host", "0.0.0.0", "--port", "8000"]