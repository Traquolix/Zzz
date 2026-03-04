FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install dependencies from pyproject.toml (single source of truth)
COPY pyproject.toml .
RUN pip install --no-cache-dir .

ENV PYTHONPATH=/app

COPY shared/ shared/
COPY config/ config/
COPY processor/main.py processor/main.py
COPY processor/processing_tools/ processor/processing_tools/
COPY processor/schema/ processor/schema/
COPY schema/ schema/

RUN touch shared/__init__.py processor/__init__.py config/__init__.py

# Run as non-root
RUN adduser --system --uid 1001 appuser && chown -R appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/healthz || exit 1

CMD ["python", "-m", "processor.main"]
