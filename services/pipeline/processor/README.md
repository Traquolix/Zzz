# Processor

Signal processing service for raw DAS (Distributed Acoustic Sensing) data. Consumes raw fiber measurements from the interrogator, applies a configurable processing chain, and outputs cleaned, decimated data for the AI Engine.

## Data Flow

```
das.raw.<fiber> (Kafka)
    │  raw channels × raw sample rate
    ▼
┌──────────────────────────────┐
│  Configurable pipeline:      │
│  Scale, Bandpass filter,     │
│  Temporal decimation,        │
│  Spatial decimation,         │
│  Common mode removal         │
│  (steps and params from      │
│   fibers.yaml)               │
└──────────────────────────────┘
    │  per-section output (decimated channels × reduced rate)
    ▼
das.processed (Kafka)
```

One input message produces N output messages — one per section defined in `fibers.yaml`.
The processing steps, their order, and all parameters are configurable per-section —
see [Configuration](#configuration) below for the current defaults.

## Key Files

```
processor/
├── main.py                         # DASProcessor (MultiTransformer), entry point
├── Dockerfile                      # Python 3.10-slim, non-root
├── schema/
│   └── das_processed_measurement.avsc  # Output Avro schema
└── processing_tools/
    ├── processing_chain.py         # ProcessingChain: orchestrates steps
    ├── step_registry.py            # Maps step names → classes
    ├── math/
    │   └── bandpass.py             # VectorizedBiquadFilter (scipy biquad)
    └── processing_steps/
        ├── base_step.py            # ProcessingStep ABC
        ├── bandpass_filter.py      # Butterworth bandpass
        ├── spatial_decimation.py   # Keep every Nth channel
        ├── temporal_decimation.py  # Keep every Nth sample
        ├── common_mode_removal.py  # Subtract spatial median
        └── scale.py               # Multiply by calibration factor
```

## Configuration

Processing steps and their parameters are defined per-section in `config/fibers.yaml`:

```yaml
defaults:
  pipeline:
    - step: scale
      params: { factor: 213.05 }
    - step: bandpass_filter
      params: { low_freq_hz: 0.3, high_freq_hz: 2.0, order: 4 }
    - step: temporal_decimation
      params: { factor: 12 }
    - step: spatial_decimation
      params: { factor: 3 }
```

Config hot-reloads — changes to `fibers.yaml` take effect without restart, including
inside Docker containers (the config file is bind-mounted from the host).

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FIBER_ID` | (none) | Filter to one fiber (e.g., `carros`). Creates consumer group `das-processor-<fiber>`. |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:29092` | Kafka broker address |
| `SCHEMA_REGISTRY_URL` | `http://schema-registry:8081` | Avro schema registry |

## Running

```bash
# Docker (standard)
make rebuild SERVICE=processor-carros

# Local development
cd services/pipeline
pip install -e .
FIBER_ID=carros python -m processor.main
```

## Design

- **Pattern:** `MultiTransformer` (1 input → N outputs, one per section)
- **Scaling:** One instance per fiber via `FIBER_ID` env var
- **State:** Processing steps maintain per-fiber state (filter coefficients, CMR warmup)
- **Health:** HTTP server on `:8080` (`/healthz`, `/readyz`, `/metrics`)
- **Errors:** Circuit breaker + exponential backoff, failed messages routed to `das.dlq`
