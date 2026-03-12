# DAS — Domain Primer

> This document explains the physics and domain concepts behind SequoIA's
> Distributed Acoustic Sensing pipeline. Read this to understand what the
> system measures, why the data looks the way it does, and what the key
> terms mean.

## What DAS Is

A DAS **interrogator** (hardware unit, ASN OptoDAS) sends laser pulses into a
standard telecom fiber optic cable. When a vehicle drives over the cable, the
vibration slightly changes the backscattered light. The interrogator measures
these changes at every point along the fiber, producing a 2D matrix:

- **Channels** (spatial axis): Each channel is a measurement point along the
  fiber, spaced ~5 meters apart. A 14 km fiber ≈ 2 800 channels. A channel is
  NOT a frequency — it's a physical location on the road.
- **Time** (temporal axis): The interrogator samples all channels simultaneously
  at 125 Hz (125 times per second).

The raw data is `[channels × time]` matrices arriving at 125 Hz. Each row is
the strain-rate signal at one point on the road. When a vehicle passes, it
creates a characteristic **V-shaped pattern** in the space-time matrix (the
"waterfall" visualization) — the slope of the V encodes the vehicle's speed.

## Key Domain Concepts

- **Fiber** — A physical fiber optic cable installation. Named by location:
  `carros` (D6202), `mathis` (Route de Turin), `promenade` (Promenade des
  Anglais). Each fiber has its own Kafka topic (`das.raw.<fiber>`), Processor
  instance, and AI Engine instance.

- **Section** — A contiguous range of channels on a fiber corresponding to a
  road segment where detection is performed. Not the entire fiber is useful —
  only portions running parallel to roads. Defined by a channel range (e.g.
  channels 1200–1716) in `fibers.yaml`.

- **Detection** — A vehicle detection event from the AI engine: timestamp,
  estimated speed (km/h), direction (positive/negative), vehicle type
  (car/truck), section ID, fiber ID.

- **DTAN** (Diffeomorphic Temporal Alignment Network) — Deep learning model for
  speed estimation. It learns to temporally align signal pairs from different
  channel positions — the time-shift needed to align them encodes vehicle speed.
  More robust than cross-correlation because it handles non-linear signal
  distortions.

- **GLRT** (Generalized Likelihood Ratio Test) — Statistical method to count
  vehicles. After DTAN estimates the speed field, GLRT identifies individual
  peaks corresponding to separate vehicles.

- **Waterfall** — The 2D visualization of DAS data (channels × time). Called
  "waterfall" because time flows downward. Vehicle passages appear as diagonal
  lines — steeper = slower vehicle.

## Data Flow

```
DAS Interrogator (125 Hz, ~2800 channels)
    → Kafka (das.raw.<fiber>)
    → Processor: bandpass filter, temporal decimation (125→10.4 Hz),
      spatial decimation (keep every 3rd channel), common mode removal
    → Kafka (das.processed)
    → AI Engine: DTAN speed estimation, GLRT peak counting,
      car/truck classification
    → Kafka (das.detections) + ClickHouse (storage)
    → Django Backend: Kafka bridge → Redis → WebSocket
    → React Frontend: live map, waterfall, stats
```

## Deployment Topology

Two servers at IMREDD (Université Côte d'Azur):

- **Backend server** (`beaujoin@192.168.99.113`): All Docker services (Kafka,
  ClickHouse, Processor, AI Engine, Django, Grafana). NVIDIA RTX 4000 Ada GPU
  for ML inference. Code at `/opt/Sequoia`.
- **Frontend server** (`frontend@134.59.98.100`): nginx serving the React
  static build at `/var/www/sequoia/`.

The DAS interrogator sits in a telco cabinet on the road and pushes raw data
directly to Kafka over the university network.
