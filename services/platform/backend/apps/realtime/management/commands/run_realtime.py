"""
Unified management command: starts the ASGI server + real-time data source.

One command to run everything needed for the backend:
  - Gunicorn with uvicorn workers (HTTP + WebSocket)
  - Data source: simulation (offline demo) or Kafka bridge (production)

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

import asyncio
import json
import threading
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.realtime.simulation import FiberConfig, run_simulation_loop


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
        source = options.get("source") or getattr(settings, "REALTIME_SOURCE", "auto")
        host = options["host"]
        port = options["port"]
        no_server = options["no_server"]
        reload = options["reload"]
        workers = options["workers"]

        if source == "auto":
            source = self._auto_detect()

        self.stdout.write(f"Data source: {source}")

        # Check if using InMemoryChannelLayer - if so, simulation must run inside the server
        channel_backend = settings.CHANNEL_LAYERS.get("default", {}).get("BACKEND", "")
        use_in_memory = "InMemoryChannelLayer" in channel_backend

        if use_in_memory and source == "sim":
            # Enable auto-start so simulation runs inside the server's event loop
            settings.REALTIME_AUTO_START_SIMULATION = True
            self.stdout.write("Using InMemoryChannelLayer: simulation will start inside server")
            if not no_server:
                self._run_server(host, port, reload, workers=1)
            else:
                self.stderr.write(
                    self.style.ERROR(
                        "Cannot run simulation without server when using InMemoryChannelLayer"
                    )
                )
        else:
            # Redis or other channel layer - can run in separate thread
            settings.REALTIME_AUTO_START_SIMULATION = False

            if source == "both":
                # Start both simulation and Kafka bridge in separate threads
                sim_thread = threading.Thread(
                    target=self._run_simulation,
                    daemon=True,
                )
                kafka_thread = threading.Thread(
                    target=self._run_kafka,
                    daemon=True,
                )
                sim_thread.start()
                kafka_thread.start()
            elif source == "kafka":
                data_thread = threading.Thread(
                    target=self._run_kafka,
                    daemon=True,
                )
                data_thread.start()
            else:
                data_thread = threading.Thread(
                    target=self._run_simulation,
                    daemon=True,
                )
                data_thread.start()

            if not no_server:
                self._run_server(host, port, reload, workers)
            else:
                # Just wait for data threads if no server
                try:
                    if source == "both":
                        sim_thread.join()
                    else:
                        data_thread.join()
                except KeyboardInterrupt:
                    self.stdout.write(self.style.WARNING("Stopped."))

    def _run_server(self, host: str, port: int, reload: bool = False, workers: int = 1):
        """Start ASGI server — uvicorn directly for dev/reload, gunicorn for production."""
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
            import sys

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

    def _run_kafka(self):
        """Run the Kafka bridge in a background thread with auto-restart."""
        import time as _time

        from apps.realtime.kafka_bridge import run_kafka_bridge_loop

        infrastructure = self._load_infrastructure()

        self.stdout.write(
            self.style.SUCCESS(
                f"Starting Kafka bridge with {len(infrastructure)} infrastructure items."
            )
        )

        while True:
            try:
                asyncio.run(run_kafka_bridge_loop(infrastructure))
                break  # Clean exit
            except KeyboardInterrupt:
                break
            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(f"Kafka bridge crashed: {exc}. Restarting in 5s...")
                )
                _time.sleep(5)

    def _run_simulation(self):
        """Run the simulation engine in a background thread."""
        fibers = self._load_fibers()
        infrastructure = self._load_infrastructure()

        self.stdout.write(
            self.style.SUCCESS(
                f"Starting simulation with {len(fibers)} fibers "
                f"and {len(infrastructure)} infrastructure items."
            )
        )

        try:
            asyncio.run(run_simulation_loop(fibers, infrastructure))
        except KeyboardInterrupt:
            pass

    def _get_data_dir(self) -> Path:
        """Get path to fiber cable data (infrastructure/clickhouse/cables/)."""
        return Path(settings.DATA_DIR) / "clickhouse" / "cables"

    def _load_fibers(self) -> list[FiberConfig]:
        """Load fiber configs from JSON data files with per-road calibration."""
        from apps.realtime.fiber_calibration import FIBER_CONFIGS

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
