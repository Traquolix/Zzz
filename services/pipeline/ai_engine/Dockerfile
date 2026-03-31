# CUDA-enabled image for GPU inference
# Using NVIDIA CUDA runtime with Python installed manually (Ubuntu 22.04 = Python 3.10)
FROM nvidia/cuda:12.4.0-runtime-ubuntu22.04

WORKDIR /app

# Proxy settings for corporate/restricted networks
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ENV http_proxy=${HTTP_PROXY} https_proxy=${HTTPS_PROXY} no_proxy=${NO_PROXY}

# Install Python 3.10 (default in Ubuntu 22.04), system dependencies,
# and CUDA compiler toolchain for JIT-compiling CPAB C++/CUDA extensions
RUN apt-get update && apt-get install -y \
    python3 \
    python3-dev \
    python3-pip \
    curl \
    libgomp1 \
    ninja-build \
    cuda-nvcc-12-4 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python

# Upgrade pip/setuptools so pyproject.toml [project] metadata is parsed correctly
# (Ubuntu 22.04 ships setuptools too old to handle PEP 621)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install PyTorch with CUDA support first (specific version for CUDA 12.4)
# Must be separate from pyproject.toml because it requires a custom index URL
RUN pip install --no-cache-dir \
    torch==2.5.1 --index-url https://download.pytorch.org/whl/cu124

# Install dependencies from pyproject.toml (single source of truth)
# Create stub packages so setuptools can resolve the package structure,
# then install with [ai] extras for torch-adjacent deps (matplotlib, pandas)
COPY pyproject.toml .
RUN mkdir -p shared config processor ai_engine \
    && touch shared/__init__.py config/__init__.py processor/__init__.py ai_engine/__init__.py \
    && pip install --no-cache-dir ".[ai]"

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
