# Plan: Pipeline Rust Migration

## Goal

Rewrite the DAS pipeline (`services/pipeline/`) from Python to Rust for lower latency,
smaller memory footprint, faster startup, smaller Docker images, and stronger type
safety. The pipeline processes ~2800 channels at 125 Hz in real-time — Rust's
zero-overhead abstractions and lack of GIL make it a natural fit.

## Scope

~10,750 lines of Python across 55 files, split into three services:
- **Shared framework** (~2,500 lines): ServiceBase, transformers, Kafka, config, health, metrics
- **Processor** (~1,200 lines): signal processing (bandpass, decimation, common mode removal)
- **AI Engine** (~3,600 lines): DTAN inference, GLRT detection, speed estimation
- **Infrastructure** (~1,500 lines): circuit breaker, retry, DLQ, OTEL, health
- **libcpab** (~2,000 lines): vendored CPAB diffeomorphic transform (PyTorch-specific)

## Key Decision: DTAN Model Inference

The DTAN model uses a custom CPAB (Continuous Piecewise-Affine Based) diffeomorphic
transform library that is deeply coupled to PyTorch. Three options:

| Option | Effort | Risk | Recommendation |
|--------|--------|------|----------------|
| **ONNX export + `ort` crate** | Medium | CPAB custom ops may not export cleanly | Recommended |
| **`tch-rs` (libtorch FFI)** | Low | Pulls in entire libtorch (~2GB), fragile C++ FFI | Fallback |
| **Reimplement DTAN in pure Rust** | Very high | Must replicate exact numerical behavior | Not recommended |

**Decision: ONNX export (Option 1)**, with `tch-rs` as fallback if CPAB operators
resist ONNX export. Validate ONNX output matches PyTorch output before proceeding.

## Rust Crate Mapping

| Python Dependency | Rust Crate | Notes |
|-------------------|-----------|-------|
| `confluent-kafka[avro]` | `rdkafka` + `apache-avro` + `schema_registry_converter` | Same librdkafka underneath |
| `numpy` / `scipy` | `ndarray` + `ndarray-linalg` | Butterworth coefficients need manual port or `biquad` crate |
| `torch` (inference) | `ort` (ONNX Runtime) | CUDA Execution Provider for GPU |
| `aiohttp` | `axum` | Health check HTTP server |
| `asyncio` | `tokio` | Async runtime |
| `pyyaml` | `serde` + `serde_yaml` | Config deserialization with derive macros |
| `opentelemetry-*` | `opentelemetry` + `opentelemetry-otlp` | Mature Rust OTEL SDK |
| `logging` | `tracing` + `tracing-subscriber` + `tracing-opentelemetry` | Structured logging |
| File watching (mtime poll) | `notify` | Proper inotify/kqueue instead of 5s polling |
| Threading locks | `parking_lot` | Faster mutexes, no poisoning |
| Collections | `crossbeam` | Lock-free channels, concurrent data structures |

## Project Structure

```
services/pipeline-rs/
  Cargo.toml                        # Workspace root
  crates/
    das-shared/                     # Framework: traits, Kafka, config, infra
      src/
        lib.rs
        service.rs                  # ServiceBase trait + pattern traits
        kafka.rs                    # rdkafka consumer/producer, Avro ser/de
        config.rs                   # FiberConfigManager (notify-based hot reload)
        message.rs                  # Message type
        circuit_breaker.rs
        retry.rs
        dlq.rs
        health.rs                   # axum /healthz endpoint
        metrics.rs                  # OTEL meters
    das-processor/                  # Signal processing service binary
      src/
        main.rs
        pipeline.rs                 # ProcessingChain executor
        steps/
          mod.rs                    # StepRegistry equivalent
          bandpass.rs               # Butterworth IIR biquad filter
          temporal_decimation.rs
          spatial_decimation.rs
          scale.rs
          common_mode_removal.rs
    das-ai-engine/                  # AI inference service binary
      src/
        main.rs
        inference.rs                # ONNX Runtime session management + GPU lock
        glrt.rs                     # GLRT detector (ndarray convolution + peaks)
        speed.rs                    # Speed estimation + outlier filtering
        detection.rs                # Detection message building
  schemas/                          # Avro .avsc files (copied from Python, shared)
    das_processed_measurement.avsc
    das_detection.avsc
    das_dlq_message.avsc
    string_key.avsc
  config/
    fibers.yaml                     # Symlink or copy from services/pipeline/config/
  docker/
    Dockerfile.processor
    Dockerfile.ai-engine
```

## Phased Migration

### Prerequisites (before writing any Rust)

These steps are done in Python and are **required** to validate the Rust port:

1. **Record test data** — Capture a few minutes of raw Kafka messages per fiber
   (`das.raw.carros`) plus the corresponding Processor output (`das.processed`) and AI
   Engine detections (`das.detections`). This becomes ground-truth for parity testing.
   Store as binary files (Avro-encoded messages).

2. **Export DTAN to ONNX** — Write a Python script:
   ```python
   model = load_dtan_model(path)
   dummy_input = torch.randn(1, N_CHANNELS, T_SAMPLES)
   torch.onnx.export(model, dummy_input, "dtan.onnx", opset_version=17)
   ```
   If CPAB custom ops fail to export, try `torch.jit.trace()` first, or fall back to
   `tch-rs`. Validate ONNX output matches PyTorch: `max |onnx - pytorch| < 1e-5`.

3. **Document Butterworth filter coefficients** — For the exact parameters used
   (0.3-2.0 Hz, order 4, fs=125 Hz), capture the SOS (second-order sections) matrix
   from `scipy.signal.butter()`. This is the ground-truth for the Rust biquad filter.
   ```python
   from scipy.signal import butter
   sos = butter(4, [0.3, 2.0], btype='bandpass', fs=125.0, output='sos')
   print(sos)  # Save these exact coefficients
   ```

4. **Pin Avro schemas** — Copy `.avsc` files to the Rust project. The Rust services
   must register identical schemas with Schema Registry.

---

### Phase 1: Shared Framework + Processor

**Goal**: Replace the Python Processor with a Rust binary. The Rust Processor produces
to `das.processed` and the Python AI Engine continues consuming from it unchanged.

**Steps**:

1. **Scaffold Cargo workspace** — Create `services/pipeline-rs/` with `das-shared` and
   `das-processor` crates. Set up CI (clippy, cargo test, cargo fmt).

2. **Port `das-shared`**:
   - `Message` struct (id, key, value as bytes, headers, timestamp)
   - Kafka setup: `rdkafka` consumer (regex topic subscription, manual commit) and
     producer (lz4, idempotent, acks=all). Avro ser/de via `apache-avro` +
     `schema_registry_converter`.
   - `ServiceBase` trait: `async fn start()`, `async fn stop()`, health check, graceful
     shutdown (tokio signal handler).
   - Transformer traits: `Transformer<T,U>`, `MultiTransformer<T,U>`,
     `BufferedTransformer<T,U>`, `RollingBufferedTransformer<T,U>`.
   - `FiberConfigManager`: load `fibers.yaml` with `serde_yaml`, watch with `notify`
     crate, `Arc<RwLock<Config>>` for thread-safe hot reload.
   - Circuit breaker, retry handler, DLQ producer.
   - Health server: `axum` on port 8080, `GET /healthz`.
   - OTEL: `tracing` + `opentelemetry-otlp` for traces and metrics.

3. **Port `das-processor`**:
   - Processing steps as trait objects (`Box<dyn ProcessingStep>`):
     - `Scale`: trivial multiply
     - `BandpassFilter`: Butterworth IIR using `biquad` crate or manual SOS
       implementation. Validate coefficients match SciPy output exactly.
     - `TemporalDecimation`: take every Nth sample (trivial)
     - `SpatialDecimation`: channel slicing (trivial)
     - `CommonModeRemoval`: median per timestamp row, subtract
   - `ProcessingChain`: sequential step execution
   - Step registry: build from `fibers.yaml` section config
   - Service: `MultiTransformer` — consume `das.raw.*`, produce to `das.processed`

4. **Parity testing**: Feed recorded raw data through both Python and Rust Processors.
   Compare output arrays element-by-element. Target: `max |rust - python| < 1e-6` for
   all processing steps.

5. **Shadow deployment**: Run Rust Processor alongside Python Processor (different
   consumer group, output to `das.processed.rust`). Compare outputs in production for
   a week. When satisfied, swap.

**Estimated scope**: ~3,500 lines of Rust (framework is more verbose than Python, but
no ML code yet).

---

### Phase 2: GLRT + Speed Estimation in Rust

**Goal**: Port the non-ML parts of the AI Engine to Rust.

**Steps**:

1. **Port GLRT detector** (`glrt_detector.py` → `glrt.rs`):
   - Element-wise correlation: adjacent channels multiplied
   - Sliding window sum: 1D convolution with box kernel (size=`glrt_win=20`)
     Use `ndarray` with a simple cumsum-based sliding window.
   - Threshold detection: contiguous intervals above threshold
   - Peak counting + car/truck classification
   - Validate against Python output on recorded data.

2. **Port speed estimation** (`vehicle_speed.py` → `speed.rs`):
   - `split_channel_overlap()`: overlapping spatial windows (step=1)
   - Speed computation from temporal shift (gauge_length * fs / shift)
   - Median aggregation, outlier rejection (min/max speed)

3. **Port detection message building** (`message_utils.py` → `detection.rs`):
   - Build `DASDetectionBatch` Avro messages
   - Direction classification, channel mapping

**Estimated scope**: ~1,500 lines of Rust.

---

### Phase 3: ONNX Inference + Full AI Engine

**Goal**: Replace the Python AI Engine entirely.

**Steps**:

1. **ONNX inference** (`inference.rs`):
   - Load ONNX model via `ort` crate
   - CUDA Execution Provider for GPU inference
   - Session management: lazy-load, LRU cache per model
   - GPU mutual exclusion: `tokio::sync::Mutex` around inference calls
   - Input preparation: channel normalization, batching
   - Output extraction: theta parameters → speed conversion

2. **Rolling buffer** (`RollingBufferedTransformer` implementation):
   - `VecDeque` per buffer key (fiber:section)
   - Window size 300, step size 250
   - Batch-process ready sections together
   - Buffer timeout (60s) for partial buffers

3. **Integration**: Wire ONNX inference → GLRT → speed filter → detection output.

4. **Parity testing**: Same recorded data, compare Python AI Engine detections vs Rust.
   Acceptable tolerance: speed within 1 km/h, same vehicle count, same direction.

5. **Shadow deployment**: Run both AI Engines in parallel for a week, compare.

**Estimated scope**: ~2,000 lines of Rust.

---

### Phase 4: Cleanup + Docker + CI

1. **Dockerfiles**: Multi-stage builds (`rust:1.XX` builder → `debian:bookworm-slim`
   runtime, or `nvidia/cuda` runtime for AI Engine with ONNX Runtime CUDA).
2. **Update `docker-compose.yml`**: Replace Python service definitions with Rust binaries.
3. **Update Makefile**: Add `make build-pipeline-rs`, integrate with `make lint` (clippy),
   `make test` (cargo test).
4. **Remove Python pipeline** (`services/pipeline/`) once Rust is validated in production.
5. **Update CLAUDE.md, ARCHITECTURE.md** with new Rust conventions.

---

## Expected Benefits

| Metric | Python (current) | Rust (expected) |
|--------|------------------|-----------------|
| Per-message latency (Processor) | ~5-10ms | ~0.5-1ms |
| Memory (Processor container) | ~300MB | ~30-50MB |
| Docker image (Processor) | ~500MB | ~50MB |
| Docker image (AI Engine) | ~8GB (CUDA+PyTorch) | ~2GB (CUDA+ONNX Runtime) |
| Startup time | 3-5s | <100ms |
| Cold start (model load) | 10-15s | 2-5s (ONNX) |

## Risks

| Risk | Mitigation |
|------|-----------|
| CPAB custom ops fail ONNX export | Fall back to `tch-rs` (libtorch FFI) for Phase 3 |
| Butterworth filter numerical divergence | Capture exact SOS coefficients from SciPy, validate coefficient-by-coefficient |
| `schema_registry_converter` crate immaturity | Test thoroughly with existing Schema Registry; fall back to raw HTTP API if needed |
| Team Rust expertise | Phase 1 is the learning investment; Processor is self-contained and low-risk |
| Avro schema compatibility | Use identical `.avsc` files, register with same Schema Registry, test cross-language consumption |

## Timeline Estimate

- **Prerequisites**: 1-2 days (data recording, ONNX export, coefficient capture)
- **Phase 1** (framework + Processor): 2-3 weeks
- **Phase 2** (GLRT + speed): 1-2 weeks
- **Phase 3** (ONNX + full AI Engine): 2-3 weeks
- **Phase 4** (Docker + CI + cleanup): 1 week
- **Total**: ~7-9 weeks for full migration, with the Python AI Engine running in
  production throughout Phases 1-2
