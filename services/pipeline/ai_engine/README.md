# AI Engine

Vehicle detection service. Consumes processed DAS data, estimates vehicle speeds using a DTAN deep learning model, counts vehicles via GLRT peak detection, and classifies them as cars or trucks.

## Data Flow

```
das.processed (Kafka)
    │  ~172 channels × 10.4 Hz (per section)
    ▼
┌──────────────────────────────────┐
│  Rolling buffer (300 samples,    │
│    250-sample step, 50 overlap)  │
│                                  │
│  DTAN inference (GPU)            │
│    → temporal alignment          │
│    → speed field estimation      │
│                                  │
│  GLRT peak detection             │
│    → vehicle counting            │
│    → car/truck classification    │
│                                  │
│  Speed filtering                 │
│    → outlier rejection           │
└──────────────────────────────────┘
    │  detections: speed, direction, count, type
    ▼
das.detections (Kafka) + ClickHouse
```

## Key Files

```
ai_engine/
├── main.py                         # AIEngineService (RollingBufferedTransformer),
│                                   #   ModelRegistry, entry point
├── message_utils.py                # Message parsing, detection message creation
├── Dockerfile                      # CUDA 12.4 + Python 3.10, non-root
├── schema/
│   └── das_detection.avsc          # Output Avro schema
└── model_vehicle/
    ├── vehicle_speed.py            # VehicleSpeedEstimator (orchestrator)
    ├── dtan_inference.py           # DTAN forward pass, alignment, speed computation
    ├── glrt_detector.py            # GLRT sliding-window correlation, peak extraction
    ├── speed_filter.py             # Per-channel outlier rejection
    ├── simple_interval_counter.py  # VehicleCounter (NN-based + GLRT fallback)
    ├── DTAN.py                     # DTAN neural network (CNN + RNN + CPAB)
    ├── model_T.py                  # Model config and weight loading
    ├── calibration.py              # Per-fiber calibration (thresholds, coupling)
    ├── visualization.py            # Waterfall plot generation
    ├── utils.py                    # Signal processing helpers
    ├── constants.py                # GLRT/speed/counting constants
    ├── models_parameters/          # Trained weights (.pth, .pt) — DO NOT MODIFY
    └── libcpab/                    # CPAB transformation library (temporal alignment)
```

## How DTAN Works

The DTAN (Diffeomorphic Temporal Alignment Network) learns to temporally align signal pairs from different channel positions along the fiber. The time-shift needed to align them encodes the vehicle speed — a vehicle passing channel A then channel B creates the same vibration pattern, shifted in time proportional to `distance / speed`.

This is more robust than traditional cross-correlation because it handles non-linear signal distortions from varying road surfaces, cable coupling, and vehicle dynamics.

## Configuration

Inference parameters are defined per-fiber in `config/fibers.yaml`:

```yaml
fibers:
  carros:
    sections:
      - name: seg1
        channels: [1200, 1716]
        model: dtan_unified
        inference:
          window_size: 300       # samples (~30s at 10.4 Hz)
          glrt_window: 20        # sliding correlation width
          min_speed_kmh: 20      # reject detections below this (noise/stopped vehicles)
          max_speed_kmh: 120     # reject detections above this (sensor artifacts)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:29092` | Kafka broker address |
| `SCHEMA_REGISTRY_URL` | `http://schema-registry:8081` | Avro schema registry |
| `CALIBRATION_PATH` | `/app/calibration` | Directory with per-fiber `.npz` calibration files |

## Running

```bash
# Docker (standard) — requires NVIDIA GPU
make rebuild SERVICE=ai-engine

# Local development
cd services/pipeline
pip install -e ".[ai]"       # Includes PyTorch + CUDA
python -m ai_engine.main

# CPU fallback (slower, minor numerical differences)
CUDA_VISIBLE_DEVICES="" python -m ai_engine.main
```

## Design

- **Pattern:** `RollingBufferedTransformer` (sliding window with overlap)
- **Scaling:** Single instance handles all fibers with per-fiber batch dispatch
- **GPU:** NVIDIA GPU required for production throughput. CPU fallback works but is slower.
- **Model registry:** LRU cache of loaded models (max 20), lazy-loaded on first use
- **Health:** HTTP server on `:8080` (`/healthz`, `/readyz`, `/metrics`)
- **Errors:** Circuit breaker + exponential backoff, failed messages routed to `das.dlq`
