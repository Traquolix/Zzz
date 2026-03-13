"""
Unified management command: starts the ASGI server + real-time data source.

One command to run everything needed for the backend:
  - Gunicorn with uvicorn workers (HTTP + WebSocket)
  - Data source: simulation (offline demo) or Kafka bridge (production)

Architecture:
  Data sources (simulation, Kafka bridge) run as separate subprocesses,
  fully decoupled from the ASGI server. Communication happens via Redis
  pub/sub — no threads, no fork() hazards.

  ┌─────────────┐  ┌─────────────┐  ┌────────────────┐
  │ Simulation   │  │ Kafka bridge │  │ Gunicorn       │
  │ subprocess   │  │ subprocess   │  │  ├─ Worker 1   │
  │   ↓          │  │   ↓          │  │  └─ Worker N   │
  │ Redis pubsub │  │ Redis pubsub │  │  Redis pubsub  │
  └──────────────┘  └──────────────┘  └────────────────┘

Usage:
    python manage.py run_realtime                # auto-detect source, serve on 0.0.0.0:8001
    python manage.py run_realtime --source sim   # force simulation
    python manage.py run_realtime --source kafka # force Kafka bridge
    python manage.py run_realtime --port 9000    # custom port
    python manage.py run_realtime --workers 4     # 4 gunicorn workers
    python manage.py run_realtime --reload       # dev mode (uvicorn with auto-reload)
    python manage.py run_realtime --no-server    # data source only (no server)

Auto-detect logic:
    - If KAFKA_BOOTSTRAP_SERVERS is set -> try Kafka, fallback to simulation
    - If not set -> simulation
"""

import atexit
import json
import multiprocessing
import os
import signal
import sys
import types
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.realtime.data_source_workers import kafka_worker, simulation_worker


class Command(BaseCommand):
    help = "Run the SequoIA backend (ASGI server + real-time data source)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            choices=["sim", "kafka", "both", "auto"],
            default=None,
            help="Data source: sim (simulation), kafka (Kafka bridge), both (sim + kafka), auto (detect). "
            "Default: uses REALTIME_SOURCE setting or auto.",
        )
        parser.add_argument(
            "--host",
            default="0.0.0.0",  # nosec B104
            help="Host to bind the ASGI server to (default: 0.0.0.0).",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=8001,
            help="Port for the ASGI server (default: 8001).",
        )
        parser.add_argument(
            "--no-server",
            action="store_true",
            default=False,
            help="Run only the data source, skip starting the ASGI server.",
        )
        parser.add_argument(
            "--reload",
            action="store_true",
            default=False,
            help="Enable auto-reload on code changes (development only).",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=1,
            help="Number of gunicorn worker processes (default: 1). "
            "Ignored when --reload is set (uses uvicorn directly).",
        )

    def handle(self, *args, **options):
        # Signal to MonitoringConfig.ready() that this is the master process
        # (before gunicorn fork or uvicorn start). Cleared before launching
        # the server so workers run the SHM warmup.
        os.environ["_SEQUOIA_SKIP_WARMUP"] = "1"

        source = options.get("source") or getattr(settings, "REALTIME_SOURCE", "auto")
        host = options["host"]
        port = options["port"]
        no_server = options["no_server"]
        reload = options["reload"]
        workers = options["workers"]

        if source == "auto":
            source = self._auto_detect()

        self.stdout.write(f"Data source: {source}")

        # Start data source subprocesses
        children: list[multiprocessing.Process] = []
        settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "sequoia.settings.prod")

        if source in ("sim", "both"):
            fibers = self._load_fibers()
            infrastructure = self._load_infrastructure()
            # Serialize FiberConfig to dicts for cross-process pickling
            fiber_dicts = [
                {
                    "id": f.id,
                    "name": f.name,
                    "color": f.color,
                    "coordinates": f.coordinates,
                    "channel_count": f.channel_count,
                    "lanes": f.lanes,
                    "speed_limit": f.speed_limit,
                    "traffic_density": f.traffic_density,
                    "typical_speed_range": f.typical_speed_range,
                    "max_channel_dir0": f.max_channel_dir0,
                    "max_channel_dir1": f.max_channel_dir1,
                }
                for f in fibers
            ]
            sim_proc = multiprocessing.Process(
                target=simulation_worker,
                args=(settings_module, fiber_dicts, infrastructure),
                daemon=True,
                name="sequoia-simulation",
            )
            children.append(sim_proc)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Starting simulation subprocess ({len(fibers)} fibers, "
                    f"{len(infrastructure)} infrastructure)"
                )
            )

        if source in ("kafka", "both"):
            infrastructure = self._load_infrastructure() if source == "kafka" else infrastructure
            kafka_proc = multiprocessing.Process(
                target=kafka_worker,
                args=(settings_module, infrastructure),
                daemon=True,
                name="sequoia-kafka-bridge",
            )
            children.append(kafka_proc)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Starting Kafka bridge subprocess ({len(infrastructure)} infrastructure)"
                )
            )

        # Close DB connections opened by _load_fibers/_load_infrastructure
        # before forking, so children don't inherit stale file descriptors.
        from django.db import connections

        connections.close_all()

        for child in children:
            child.start()

        # Graceful shutdown: terminate children when the parent exits.
        # We use both atexit (survives gunicorn overwriting signal handlers)
        # and signal handlers (works for --reload/--no-server paths).
        def _terminate_children_cleanup() -> None:
            for child in children:
                if child.is_alive():
                    child.terminate()
                    child.join(timeout=5)

        atexit.register(_terminate_children_cleanup)

        def _terminate_children_signal(signum: int, frame: types.FrameType | None) -> None:
            _terminate_children_cleanup()
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)

        signal.signal(signal.SIGTERM, _terminate_children_signal)
        signal.signal(signal.SIGINT, _terminate_children_signal)

        if not no_server:
            self._run_server(host, port, reload, workers)
        else:
            # Wait for data source subprocesses
            try:
                for child in children:
                    child.join()
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("Stopped."))

    def _run_server(self, host: str, port: int, reload: bool = False, workers: int = 1):
        """Start ASGI server — uvicorn directly for dev/reload, gunicorn for production."""
        # Clear skip flag so server processes (gunicorn workers / uvicorn)
        # run the SHM cache warmup in MonitoringConfig.ready().
        os.environ.pop("_SEQUOIA_SKIP_WARMUP", None)

        if reload:
            import uvicorn

            self.stdout.write(self.style.SUCCESS(f"ASGI server starting on {host}:{port} (reload)"))
            uvicorn.run(
                "sequoia.asgi:application",
                host=host,
                port=port,
                reload=True,
                reload_dirs=[str(Path(__file__).resolve().parent.parent.parent.parent)],
                log_level="info",
                lifespan="off",
            )
        else:
            from gunicorn.app.wsgiapp import WSGIApplication

            self.stdout.write(
                self.style.SUCCESS(
                    f"ASGI server starting on {host}:{port} "
                    f"({workers} worker{'s' if workers > 1 else ''})"
                )
            )
            sys.argv = [
                "gunicorn",
                "sequoia.asgi:application",
                "--bind",
                f"{host}:{port}",
                "--workers",
                str(workers),
                "--worker-class",
                "uvicorn.workers.UvicornWorker",
                "--timeout",
                "0",
                "--graceful-timeout",
                "10",
                "--log-level",
                "info",
            ]
            WSGIApplication().run()

    def _auto_detect(self) -> str:
        """Detect whether Kafka is available, fallback to simulation."""
        kafka_servers = getattr(settings, "KAFKA_BOOTSTRAP_SERVERS", "")
        if not kafka_servers:
            self.stdout.write("No KAFKA_BOOTSTRAP_SERVERS configured -> simulation mode")
            return "sim"

        # Check if confluent-kafka is installed
        try:
            import confluent_kafka  # noqa: F401
        except ImportError:
            self.stdout.write(
                "confluent-kafka not installed -> simulation mode\n"
                "  Install with: pip install confluent-kafka"
            )
            return "sim"

        # Quick connectivity check
        try:
            from confluent_kafka.admin import AdminClient

            admin = AdminClient({"bootstrap.servers": kafka_servers})
            metadata = admin.list_topics(timeout=3)
            topic_names = list(metadata.topics.keys())
            self.stdout.write(
                f"Kafka reachable at {kafka_servers} "
                f"({len(topic_names)} topics) -> both mode (sim + kafka)"
            )
            return "both"
        except Exception as e:
            self.stdout.write(f"Kafka unreachable ({e}) -> simulation mode")
            return "sim"

    def _get_data_dir(self) -> Path:
        """Get path to fiber cable data (infrastructure/clickhouse/cables/)."""
        return Path(settings.DATA_DIR) / "clickhouse" / "cables"

    def _load_fibers(self) -> list:
        """Load fiber configs from JSON data files with per-road calibration."""
        from apps.realtime.fiber_calibration import FIBER_CONFIGS
        from apps.realtime.simulation import FiberConfig

        data_dir = self._get_data_dir()

        fibers = []
        for fiber_id, cfg in FIBER_CONFIGS.items():
            path = data_dir / f"{fiber_id}.json"
            if not path.exists():
                self.stderr.write(f"Warning: {path} not found, skipping")
                continue

            with open(path) as f:
                data = json.load(f)

            coords = [c for c in data["coordinates"] if c[0] is not None and c[1] is not None]

            fibers.append(
                FiberConfig(
                    id=data["id"],
                    name=data["name"],
                    color=data.get("color", "#000000"),
                    coordinates=coords,
                    channel_count=len(coords),
                    lanes=cfg["lanes"],
                    speed_limit=cfg["speed_limit"],
                    traffic_density=cfg["traffic_density"],
                    typical_speed_range=cfg["typical_speed_range"],
                    max_channel_dir0=cfg["max_channel_dir0"],
                    max_channel_dir1=cfg["max_channel_dir1"],
                )
            )
            max_ch_0 = cfg["max_channel_dir0"] or len(coords)
            max_ch_1 = cfg["max_channel_dir1"] or len(coords)
            self.stdout.write(
                f"  Loaded {data['name']} ({len(coords)} channels, "
                f"dir0≤{max_ch_0}, dir1≤{max_ch_1}, "
                f"{cfg['speed_limit']}km/h, {cfg['traffic_density']} density)"
            )

        return fibers

    def _load_infrastructure(self) -> list[dict]:
        """Load infrastructure from PostgreSQL (includes organization_id for org-scoped SHM)."""
        from apps.monitoring.models import Infrastructure

        items = []
        for infra in Infrastructure.objects.select_related("organization").all():
            items.append(
                {
                    "id": infra.id,
                    "type": infra.type,
                    "name": infra.name,
                    "fiber_id": infra.fiber_id,
                    "start_channel": infra.start_channel,
                    "end_channel": infra.end_channel,
                    "organization_id": str(infra.organization_id),
                }
            )

        if items:
            self.stdout.write(f"  Loaded {len(items)} infrastructure items from DB")
        else:
            # Fallback to JSON file if DB is empty
            path = self._get_data_dir() / "infrastructure.json"
            if path.exists():
                with open(path) as f:
                    items = json.load(f)
                self.stdout.write(
                    f"  Loaded {len(items)} infrastructure items from JSON (no org_id)"
                )

        return items
