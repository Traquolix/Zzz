"""
Unified management command: starts the ASGI server + real-time data source.

One command to run everything needed for the backend:
  - Daphne ASGI server (HTTP + WebSocket)
  - Data source: simulation (offline demo) or Kafka bridge (production)

Usage:
    python manage.py run_realtime                # auto-detect source, serve on 0.0.0.0:8001
    python manage.py run_realtime --source sim   # force simulation
    python manage.py run_realtime --source kafka # force Kafka bridge
    python manage.py run_realtime --port 9000    # custom port
    python manage.py run_realtime --no-server    # data source only (no Daphne)

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
            choices=["sim", "kafka", "auto"],
            default=None,
            help="Data source: sim (simulation), kafka (Kafka bridge), auto (detect). "
            "Default: uses REALTIME_SOURCE setting or auto.",
        )
        parser.add_argument(
            "--host",
            default="0.0.0.0",
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

    def handle(self, *args, **options):
        source = options.get("source") or getattr(settings, "REALTIME_SOURCE", "auto")
        host = options["host"]
        port = options["port"]
        no_server = options["no_server"]

        if source == "auto":
            source = self._auto_detect()

        self.stdout.write(f"Data source: {source}")

        # Check if using InMemoryChannelLayer - if so, simulation must run inside Daphne
        channel_backend = settings.CHANNEL_LAYERS.get("default", {}).get("BACKEND", "")
        use_in_memory = "InMemoryChannelLayer" in channel_backend

        if use_in_memory and source == "sim":
            # Enable auto-start so simulation runs inside Daphne's event loop
            settings.REALTIME_AUTO_START_SIMULATION = True
            self.stdout.write("Using InMemoryChannelLayer: simulation will start inside Daphne")
            if not no_server:
                self._run_daphne(host, port)
            else:
                self.stderr.write(
                    self.style.ERROR(
                        "Cannot run simulation without server when using InMemoryChannelLayer"
                    )
                )
        else:
            # Redis or other channel layer - can run in separate thread
            settings.REALTIME_AUTO_START_SIMULATION = False

            if source == "kafka":
                data_thread = threading.Thread(
                    target=self._run_kafka,
                    daemon=True,
                )
            else:
                data_thread = threading.Thread(
                    target=self._run_simulation,
                    daemon=True,
                )
            data_thread.start()

            # Run Daphne in the main thread (it handles signals properly)
            if not no_server:
                self._run_daphne(host, port)
            else:
                # Just wait for the data thread if no server
                try:
                    data_thread.join()
                except KeyboardInterrupt:
                    self.stdout.write(self.style.WARNING("Stopped."))

    def _run_daphne(self, host: str, port: int):
        """Start Daphne ASGI server in the main thread."""
        from daphne.endpoints import build_endpoint_description_strings
        from daphne.server import Server

        from sequoia.asgi import application

        self.stdout.write(self.style.SUCCESS(f"ASGI server starting on {host}:{port}"))

        endpoints = build_endpoint_description_strings(host=host, port=port)
        server = Server(
            application=application,
            endpoints=endpoints,
        )
        server.run()

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
                f"Kafka reachable at {kafka_servers} ({len(topic_names)} topics) -> kafka mode"
            )
            return "kafka"
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
        return settings.DATA_DIR / "clickhouse" / "cables"

    def _load_fibers(self) -> list[FiberConfig]:
        """Load fiber configs from JSON data files."""
        data_dir = self._get_data_dir()

        fiber_files = [
            ("carros.json", {"lanes": 6, "speed_limit": 110, "traffic_density": "high"}),
            ("promenade.json", {"lanes": 4, "speed_limit": 50, "traffic_density": "medium"}),
            ("mathis.json", {"lanes": 4, "speed_limit": 90, "traffic_density": "low"}),
        ]

        fibers = []
        for filename, config in fiber_files:
            path = data_dir / filename
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
                    **config,
                )
            )
            self.stdout.write(f"  Loaded {data['name']} ({len(coords)} channels)")

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
