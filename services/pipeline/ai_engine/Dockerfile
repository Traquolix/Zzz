# CUDA-enabled image for GPU inference
# Using NVIDIA PyTorch base image with CUDA 12.4 support
FROM nvidia/cuda:12.4.0-runtime-ubuntu22.04

WORKDIR /app

# Install Python 3.10 (default in Ubuntu 22.04) and system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-dev \
    python3-pip \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python

# Install PyTorch with CUDA support first (specific version for CUDA 12.4)
RUN pip install --no-cache-dir \
    torch==2.5.1 --index-url https://download.pytorch.org/whl/cu124

# Install remaining Python dependencies for AI engine
RUN pip install --no-cache-dir \
    confluent-kafka[avro] \
    aiohttp==3.9.1 \
    opentelemetry-api==1.24.0 \
    opentelemetry-sdk==1.24.0 \
    opentelemetry-exporter-otlp==1.24.0 \
    opentelemetry-instrumentation-logging==0.45b0 \
    opentelemetry-propagator-b3==1.24.0 \
    numpy>=1.21.0 \
    scipy>=1.7.0 \
    matplotlib>=3.5.0 \
    pandas \
    pyyaml

# Set Python path and suppress NNPACK warning (CPU-only optimization not available)
ENV PYTHONPATH=/app
ENV NNPACK_SUPPRESS_WARNINGS=1
ENV PYTHONWARNINGS="ignore::UserWarning"

# Copy shared dependencies
COPY shared/ shared/
COPY config/ config/

# AI Engine specific files
COPY ai_engine/main.py ai_engine/main.py
COPY ai_engine/message_utils.py ai_engine/message_utils.py
COPY ai_engine/schema/ ai_engine/schema/
COPY schema/ schema/

# AI Model dependencies
COPY ai_engine/model_vehicle/ ai_engine/model_vehicle/

# Create __init__.py files for proper Python module imports
RUN touch shared/__init__.py ai_engine/__init__.py config/__init__.py

# Run as non-root
RUN adduser --system --uid 1001 appuser && chown -R appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8080/healthz || exit 1

CMD ["python", "-m", "ai_engine.main"]
