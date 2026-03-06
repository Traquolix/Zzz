# Plan: Standardized Dev Environment

## Goal

A new developer clones the repo, runs `make dev`, and has a working system in
minutes. No GPU, no DAS hardware, no manual secret generation.

Two modes depending on what you're working on:

- **`make dev`** — lightweight simulation mode. Backend + frontend only. For UI/UX
  work, demos, and laptops without a GPU. No Kafka, no pipeline services.
- **`make dev-full`** — full pipeline with recorded test data replay. For pipeline
  development, integration testing, and non-regression checks. Needs Docker but
  no live DAS hardware. Uses GPU if available, falls back to CPU if not (slower,
  slightly different numerics — but the full data flow still runs). GPU-specific
  issues are caught in preprod.

## What Already Works

The Django dev settings (`settings/dev.py`) are already lightweight:
- SQLite instead of PostgreSQL
- In-memory channel layer instead of Redis
- In-memory cache instead of Redis
- Auto-generated JWT keys
- `REALTIME_AUTO_START_SIMULATION = True` — simulation starts on first WebSocket
  connection
- No Kafka dependency

So `make dev` for simulation mode is close — it just needs a clean entrypoint.

## What's Missing

### For `make dev` (simulation mode)

1. **No `make dev` target** — there's `make up` which starts the whole Docker stack.
   Need a lightweight command that starts only backend + frontend.
2. **ClickHouse still required** — the backend queries ClickHouse for historical
   data. In dev/simulation mode, these queries should gracefully return empty results
   or the backend should skip ClickHouse when unavailable.
3. **No dev seed data** — a new dev gets an empty database with no user account.
   Need a `make seed` that creates a superuser + demo organization + fiber config.
4. **Frontend needs `npm install`** — should be documented or automated.

### For `make dev-full` (replay mode)

1. **No test DAS recording** — need a sample of real (or realistic) DAS data.
2. **No replay tool** — need a script that reads the recording and publishes to Kafka
   at the original rate.
3. **GPU requirement for AI Engine** — need a CPU-fallback mode or pre-computed
   expected outputs.
4. **No expected outputs** — need a "golden file" of expected detections for the test
   recording to enable non-regression testing.

## Test DAS Recording

### What to record

A 5-minute window of raw DAS data from the Carros fiber during a period with
visible traffic (e.g., weekday morning). This gives:
- Multiple vehicle passages at different speeds
- Both directions
- Mix of cars and trucks
- Enough data for the AI Engine's 30-second sliding window to produce several
  detection cycles

### Size estimate

Raw data: 2830 channels x 125 Hz x 4 bytes (float32) = ~1.4 MB/s.
5 minutes = ~420 MB uncompressed.

This is too large for git. Options:

1. **Git LFS** — store the recording in LFS. ~420 MB uncompressed, ~150-200 MB
   with lz4 compression. Acceptable for LFS.
2. **Shorter recording** — 1 minute = ~84 MB uncompressed, ~30-40 MB compressed.
   Still enough for several detection windows. Much more manageable.
3. **Record post-processor output** — the processed data (after decimation) is much
   smaller: ~172 channels x 10.4 Hz x 4 bytes = ~7 KB/s. 5 minutes = ~2 MB. This
   skips the processor but tests the AI Engine and everything downstream.
4. **Both** — a small raw recording (1 min) for full-pipeline tests, plus a longer
   processed recording (5 min) for AI Engine + backend tests.

**Recommendation:** Option 4. Store in `data/test-recordings/` with Git LFS for
the raw recording. The processed recording is small enough for plain git.

### File format

Store as Avro files (same serialization as Kafka). The replay script reads frames
from the file and publishes them to Kafka with original timing. This way the
replay uses the exact same code path as production.

```
data/test-recordings/
  raw_carros_1min.avro       # ~30-40 MB compressed (Git LFS)
  processed_carros_5min.avro # ~2 MB (plain git)
  expected_detections.json   # golden file: expected AI Engine output
  README.md                  # recording date, conditions, what to expect
```

### How to capture

Record directly from Kafka on the production server:

```bash
# On backend server — dump 1 minute of raw messages from das.raw.carros
# Using kafkacat/kcat or a small Python script with confluent-kafka
python scripts/record_kafka.py \
  --topic das.raw.carros \
  --duration 60 \
  --output data/test-recordings/raw_carros_1min.avro

# Same for processed data, longer duration
python scripts/record_kafka.py \
  --topic das.processed \
  --duration 300 \
  --output data/test-recordings/processed_carros_5min.avro
```

The recording script needs to be written. It's a simple Kafka consumer that writes
messages to an Avro file with their original timestamps.

### Golden file for non-regression

After the first successful replay, capture the AI Engine's detection output:

```bash
python scripts/record_kafka.py \
  --topic das.detections \
  --duration 300 \
  --output data/test-recordings/expected_detections.json
```

Future replays compare their output against this golden file. The comparison should
be fuzzy (allow small floating-point differences in speed) but strict on:
- Number of detections
- Vehicle types (car/truck)
- Direction
- Speed within +/- 2 km/h

The golden file should be generated from a GPU run (production or preprod). CPU
runs may produce slightly different values due to floating-point differences, so
the comparison tolerance should be wider for CPU (e.g., speed within +/- 5 km/h)
or use a separate CPU golden file.

## Implementation Steps

### Prerequisites (one-time setup)

Before running `make dev`, developers need Python 3.10 and Node.js 20+ installed.
First-time setup:

```bash
# Backend
cd services/platform/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd services/platform/frontend
npm install
```

These are one-time steps. `make dev-frontend` runs `npm install` as a no-op fast
check, but the backend venv must be set up manually.

### Phase 1: `make dev` (simulation mode)

- [ ] Add Makefile targets and Procfile.dev:
      ```makefile
      dev-backend:
          cd services/platform/backend && \
            DJANGO_SETTINGS_MODULE=sequoia.settings.dev \
            python manage.py migrate && \
            python manage.py seed_dev --no-input && \
            python manage.py run_realtime --host 0.0.0.0 --port 8001

      dev-frontend:
          cd services/platform/frontend && npm install && npm run dev

      dev:
          @if command -v overmind >/dev/null 2>&1; then \
            overmind start -f Procfile.dev; \
          else \
            echo "Run in two terminals:"; \
            echo "  make dev-backend"; \
            echo "  make dev-frontend"; \
            echo ""; \
            echo "Or install overmind for a single-command experience:"; \
            echo "  brew install overmind  (macOS)"; \
            echo "  Then: make dev"; \
          fi
      ```
      ```
      # Procfile.dev
      backend: cd services/platform/backend && DJANGO_SETTINGS_MODULE=sequoia.settings.dev python manage.py migrate && python manage.py seed_dev --no-input && python manage.py run_realtime --host 0.0.0.0 --port 8001
      frontend: cd services/platform/frontend && npm install && npm run dev
      ```
      If overmind is installed, `make dev` starts both with labeled colored output
      and supports `overmind connect backend` / `overmind restart frontend`.
      If not, it falls back to printing two-terminal instructions. Zero hard
      dependencies either way.
- [ ] Handle missing ClickHouse gracefully in dev — catch connection errors in
      `apps.shared.clickhouse.query()` and return empty results when
      `ENVIRONMENT=development`
- [ ] Add `make seed` target — creates superuser, demo org, assigns fibers:
      ```bash
      python manage.py seed_dev  # custom management command
      ```
- [ ] Document in CONTRIBUTING.md: "Getting Started" section with `make dev`

### Phase 2: Test Recording Infrastructure

- [ ] Write `scripts/record_kafka.py` — Kafka consumer that dumps messages to
      Avro files with timestamps
- [ ] Write `scripts/replay_kafka.py` — reads Avro file, publishes to Kafka at
      original rate (or configurable speedup)
- [ ] Set up Git LFS for `data/test-recordings/*.avro` files over 10 MB
- [ ] Capture initial recordings from production (raw 1 min + processed 5 min)

> **Note:** Capturing recordings requires SSH access to the production backend server
> and a period with visible traffic. This is a one-time maintainer task, not part of
> automated setup. The recordings are committed to the repo (LFS for large files) so
> other developers get them on `git clone`.

### Phase 3: `make dev-full` (replay mode)

- [ ] Add `make dev-full` Makefile target — starts Kafka + Schema Registry +
      ClickHouse + PostgreSQL + Backend via Docker Compose (dev profile), then
      starts replay
- [ ] AI Engine CPU fallback: check if GPU is available, fall back to CPU inference
      (slower but functional, minor numerical differences). PyTorch already
      supports this — just needs `device = "cuda" if torch.cuda.is_available()
      else "cpu"`. GPU-specific issues are caught in preprod, not here.
- [ ] Docker Compose dev profile: starts only infrastructure (Kafka + Schema Registry +
      ClickHouse + PostgreSQL + Redis). Processor and AI Engine run on the host by
      default (`python -m processor`, `python -m ai_engine`) for easier debugging
      and log visibility. Optionally run them in Docker if a GPU is available and
      host setup is inconvenient — but host is the primary dev workflow.
- [ ] `.env.dev` for Docker: pre-filled secrets (hardcoded dummy passwords — this
      is local Docker, security doesn't matter)

### Phase 4: Non-Regression Testing

- [ ] Capture golden file after first successful replay
- [ ] Write `scripts/compare_detections.py` — compares replay output against
      golden file with fuzzy matching
- [ ] Add `make test-regression` target — replays recording, captures output,
      compares against golden file
- [ ] Integrate into CI (requires Docker stack in CI runner, or run as a
      separate integration test job on the self-hosted backend runner)

## `make dev` End-to-End Flow

**With overmind (single terminal):**
```
$ git clone git@github.com:Traquolix/Sequoia.git && cd Sequoia
$ make dev

  backend  | Applying migrations... OK
  backend  | Seeding dev data... admin@sequoia.dev / password
  backend  | Starting SequoIA backend (ASGI + simulation)...
  frontend | VITE v6.2.0  ready in 342 ms
  frontend |   ➜  Local: http://localhost:5173/

  Backend:  http://localhost:8001
  Frontend: http://localhost:5173
  Login:    admin@sequoia.dev / password

  Useful commands:
    overmind connect backend    # attach to backend (own terminal)
    overmind restart frontend   # restart frontend only
    ctrl-C                      # stop everything
```

**Without overmind (two terminals):**
```
$ git clone git@github.com:Traquolix/Sequoia.git && cd Sequoia

# Terminal 1:
$ make dev-backend
  → python manage.py migrate (SQLite)
  → python manage.py seed_dev (creates admin@sequoia.dev / password)
  → python manage.py run_realtime (Django + simulation)

# Terminal 2:
$ make dev-frontend
  → npm install && npm run dev (frontend with HMR)
```

## `make dev-full` End-to-End Flow

```
$ make dev-full

  → docker compose --profile dev up -d
    (starts Kafka, Schema Registry, ClickHouse, PostgreSQL, Redis)
  → python manage.py migrate (PostgreSQL)
  → python manage.py seed_dev
  → python scripts/replay_kafka.py --input data/test-recordings/raw_carros_1min.avro
    (publishes test data to Kafka)
  → processor and AI engine consume from Kafka, process, write detections
  → backend picks up detections via Kafka bridge → WebSocket → frontend

  Full pipeline running with real (recorded) DAS data.
  Uses GPU if available, CPU fallback otherwise. No DAS interrogator needed.
```

## Order of Work

1. **`make dev`** (Phase 1) — highest value, lowest effort. Unblocks frontend
   development and demos immediately.
2. **Recording infra** (Phase 2) — capture test data while you have server access.
   Can be done independently.
3. **`make dev-full`** (Phase 3) — depends on Phase 2 recordings.
4. **Non-regression** (Phase 4) — depends on Phase 3 being stable.
