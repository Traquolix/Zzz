"""
Management command: snap fiber coordinates to road geometry.

Usage:
    python manage.py snap_fibers_to_roads --token=pk.xxx
    python manage.py snap_fibers_to_roads --token=pk.xxx --fiber-id=carros
    python manage.py snap_fibers_to_roads --token=pk.xxx --dry-run
    python manage.py snap_fibers_to_roads --token=pk.xxx --radius=15

Reads fiber coordinates from JSON cable files, calls Mapbox Map Matching API
to snap to nearest roads, then writes `directional_paths` back to the JSON
files. The frontend will receive `coordsPrecomputed=true` and use the
snapped coordinates directly.

The snap is idempotent — re-running overwrites previous snapped coordinates.
"""

import json
import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.fibers.road_snap import (
    DEFAULT_RADIUS,
    load_snap_config,
    snap_directional,
    snap_directional_segmented,
)
from apps.fibers.views import _CABLE_FILES, _get_cables_dir, _load_fibers_from_json

logger = logging.getLogger("sequoia.fibers")


class Command(BaseCommand):
    help = "Snap fiber coordinates to road geometry via Mapbox Map Matching API"

    def add_arguments(self, parser):
        parser.add_argument(
            "--token",
            required=True,
            help="Mapbox access token (server-side, not the frontend VITE_ token)",
        )
        parser.add_argument(
            "--fiber-id",
            help='Snap only a specific physical fiber ID (e.g., "carros"). Default: all fibers.',
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be snapped without writing to storage.",
        )
        parser.add_argument(
            "--offset-meters",
            type=float,
            default=12.0,
            help="Perpendicular offset in meters for each direction (default: 12).",
        )
        parser.add_argument(
            "--radius",
            type=int,
            default=DEFAULT_RADIUS,
            help=f"Search radius in meters for road matching (default: {DEFAULT_RADIUS}).",
        )
        parser.add_argument(
            "--config-dir",
            type=str,
            default=None,
            help="Directory containing per-fiber snap YAML configs (default: infrastructure/clickhouse/cables/).",
        )

    def handle(self, *args, **options):
        token = options["token"]
        target_fiber = options.get("fiber_id")
        dry_run = options.get("dry_run", False)
        offset_meters = options.get("offset_meters", 12.0)
        radius = options.get("radius", DEFAULT_RADIUS)

        # Resolve config directory
        config_dir_opt = options.get("config_dir")
        if config_dir_opt:
            config_dir = Path(config_dir_opt)
        else:
            config_dir = _get_cables_dir()

        # Load fibers (physical cables, pre-expansion)
        fibers = self._load_physical_fibers(target_fiber)

        if not fibers:
            raise CommandError("No fibers found to snap.")

        self.stdout.write(f"Found {len(fibers)} fiber(s) to process.")
        self.stdout.write(f"Settings: radius={radius}m, default offset={offset_meters}m")
        self.stdout.write(f"Config dir: {config_dir}")

        for fiber in fibers:
            fiber_id = fiber["id"]
            coords = fiber.get("coordinates", [])

            if len(coords) < 2:
                self.stdout.write(
                    self.style.WARNING(f"  {fiber_id}: skipped (only {len(coords)} coordinates)")
                )
                continue

            valid_count = sum(1 for c in coords if c and c[0] is not None)
            self.stdout.write(
                f"  {fiber_id}: {len(coords)} channels ({valid_count} with coordinates)"
            )

            # Check for per-segment YAML config
            config_path = config_dir / f"{fiber_id}_snap.yaml"
            if config_path.exists():
                self.stdout.write(f"  {fiber_id}: using config {config_path.name}")
                try:
                    config = load_snap_config(config_path)
                except ValueError as e:
                    self.stdout.write(self.style.ERROR(f"  {fiber_id}: invalid config — {e}"))
                    continue

                segments = config.get("segments", [])
                self.stdout.write(f"  {fiber_id}: {len(segments)} segment(s) defined")
                for seg in segments:
                    ch = seg["channels"]
                    d0 = seg["direction_0"]["offset_meters"]
                    d1 = seg["direction_1"]["offset_meters"]
                    self.stdout.write(f"    channels [{ch[0]}, {ch[1]}]: dir0={d0}m, dir1={d1}m")

                dir_paths = snap_directional_segmented(
                    coords,
                    token,
                    config=config,
                    radius=radius,
                )
            else:
                self.stdout.write(
                    f"  {fiber_id}: no config file, using uniform offset ±{offset_meters}m"
                )
                dir_paths = snap_directional(
                    coords,
                    token,
                    offset_meters=offset_meters,
                    radius=radius,
                )

            if dir_paths is None:
                self.stdout.write(self.style.ERROR(f"  {fiber_id}: snap FAILED"))
                continue

            for d in ["0", "1"]:
                snapped_valid = sum(1 for c in dir_paths[d] if c and c[0] is not None)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  {fiber_id} dir {d}: snapped ({snapped_valid} coords mapped to roads)"
                    )
                )

            if dry_run:
                self.stdout.write(f"  {fiber_id}: dry-run, not writing to storage")
                self._print_sample(coords, dir_paths["0"], dir_paths["1"])
                continue

            self._write_fiber(fiber_id, dir_paths)
            self.stdout.write(self.style.SUCCESS(f"  {fiber_id}: written to storage"))

        self.stdout.write(self.style.SUCCESS("\nDone."))

    def _load_physical_fibers(self, target_fiber=None):
        """Load physical fiber data (pre-directional-expansion)."""
        fibers = _load_fibers_from_json()
        self.stdout.write("Loaded fibers from JSON.")

        if not fibers:
            return []

        # fibers from views are already expanded to directional.
        # We need physical (deduplicate by parentFiberId).
        seen = {}
        for f in fibers:
            parent_id = f.get("parentFiberId", f["id"])
            if parent_id not in seen:
                seen[parent_id] = {
                    "id": parent_id,
                    "coordinates": f["coordinates"],
                    "name": f.get("name", parent_id),
                }

        if target_fiber:
            return [v for k, v in seen.items() if k == target_fiber]

        return list(seen.values())

    def _write_fiber(self, fiber_id, directional_paths):
        """Write snapped directional paths back to the JSON cable files."""
        cables_dir = _get_cables_dir()

        for cable_file in _CABLE_FILES:
            path = cables_dir / cable_file
            if not path.exists():
                continue

            with open(path) as f:
                data = json.load(f)

            if data.get("id") != fiber_id:
                continue

            # Store directional paths in the cable JSON
            data["directional_paths"] = {
                "0": directional_paths["0"],
                "1": directional_paths["1"],
            }

            with open(path, "w") as f:
                json.dump(data, f, indent=2)

            logger.info(
                "Wrote snapped directional paths for fiber %s to %s "
                "(dir0: %d coords, dir1: %d coords)",
                fiber_id,
                cable_file,
                len(directional_paths["0"]),
                len(directional_paths["1"]),
            )
            return

        logger.warning("No JSON cable file found for fiber %s", fiber_id)

    def _print_sample(self, original, snapped_0, snapped_1):
        """Print a few sample coordinates for dry-run verification."""
        self.stdout.write("    Direction 0:")
        for i in [0, 1, len(original) // 2, -2, -1]:
            idx = i if i >= 0 else len(original) + i
            if 0 <= idx < len(original) and 0 <= idx < len(snapped_0):
                o = original[idx]
                s = snapped_0[idx]
                o_str = f"[{o[0]:.6f}, {o[1]:.6f}]" if o[0] is not None else "[null]"
                s_str = f"[{s[0]:.6f}, {s[1]:.6f}]" if s[0] is not None else "[null]"
                self.stdout.write(f"      ch{idx}: {o_str} -> {s_str}")

        self.stdout.write("    Direction 1:")
        for i in [0, 1, len(original) // 2, -2, -1]:
            idx = i if i >= 0 else len(original) + i
            if 0 <= idx < len(original) and 0 <= idx < len(snapped_1):
                o = original[idx]
                s = snapped_1[idx]
                o_str = f"[{o[0]:.6f}, {o[1]:.6f}]" if o[0] is not None else "[null]"
                s_str = f"[{s[0]:.6f}, {s[1]:.6f}]" if s[0] is not None else "[null]"
                self.stdout.write(f"      ch{idx}: {o_str} -> {s_str}")
