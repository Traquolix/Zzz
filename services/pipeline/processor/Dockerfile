FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "confluent-kafka[avro]" \
    aiohttp==3.9.1 \
    opentelemetry-api==1.24.0 \
    opentelemetry-sdk==1.24.0 \
    opentelemetry-exporter-otlp==1.24.0 \
    opentelemetry-instrumentation-logging==0.45b0 \
    opentelemetry-propagator-b3==1.24.0 \
    scipy numpy pyyaml

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
