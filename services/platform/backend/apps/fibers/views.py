"""
Fiber data views — reads from ClickHouse fiber_cables table.

Falls back to JSON cable files when ClickHouse is unavailable
(e.g. during local development or simulation-only demo).

Data is org-scoped: non-superusers only see fibers assigned to their
organization via FiberAssignment. Superusers see all fibers.

Each physical cable is expanded into two directional fibers (direction 0 and 1)
before returning to the frontend, so that sections, landmarks, and interactions
are per-direction.
"""

import json
import logging
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fibers.serializers import FiberLineSerializer
from apps.fibers.utils import get_org_fiber_ids
from apps.shared.clickhouse import get_client
from apps.shared.permissions import IsActiveUser
from apps.shared.exceptions import ClickHouseUnavailableError

FIBERS_CACHE_TTL = 5 * 60  # 5 minutes

logger = logging.getLogger('sequoia')

_CABLE_FILES = [
    'carros.json',
    'promenade.json',
    'mathis.json',
]


def _fiber_cache_key(user):
    if user.is_superuser:
        return 'fibers:all'
    return f'fibers:org:{user.organization_id}'


def _get_cables_dir() -> Path:
    return settings.DATA_DIR / 'clickhouse' / 'cables'


def _expand_to_directional(fiber: dict) -> list[dict]:
    """Expand a single physical fiber into two directional fibers (direction 0 and 1).

    If `directional_paths` is provided in the fiber data with matching channel counts,
    those explicit coordinates are used. Otherwise, the frontend will compute
    perpendicular offsets from the base coordinates.

    Expected structure for explicit paths:
        "directional_paths": {
            "0": [[lng, lat], ...],  // path for direction 0
            "1": [[lng, lat], ...]   // path for direction 1
        }
    """
    parent_id = fiber['id']
    base_coords = fiber['coordinates']
    directional_paths = fiber.get('directional_paths', {})
    result = []

    for direction in (0, 1):
        dir_key = str(direction)
        explicit_path = directional_paths.get(dir_key)

        # Use explicit path if provided and has matching channel count
        if explicit_path and len(explicit_path) == len(base_coords):
            coords = explicit_path
            coords_precomputed = True
        else:
            coords = base_coords
            coords_precomputed = False

        result.append({
            'id': f'{parent_id}:{direction}',
            'parentFiberId': parent_id,
            'direction': direction,
            'name': fiber['name'],
            'color': fiber['color'],
            'coordinates': coords,
            'coordsPrecomputed': coords_precomputed,  # True = don't apply offset on frontend
            'landmarks': fiber.get('landmarks'),
        })
    return result


def _load_fibers_from_json(fiber_ids: list[str] | None = None) -> list[dict]:
    """Load fiber data from JSON cable files (fallback when ClickHouse is unavailable).

    Returns directional fibers (two per physical cable).
    """
    cables_dir = _get_cables_dir()
    fibers = []

    for cable_file in _CABLE_FILES:
        path = cables_dir / cable_file
        if not path.exists():
            continue

        with open(path) as f:
            data = json.load(f)

        fid = data['id']
        if fiber_ids is not None and fid not in fiber_ids:
            continue

        # Include all coordinates (valid + null) to preserve channel indexing.
        physical = {
            'id': fid,
            'name': data.get('name', fid),
            'color': data.get('color', '#888888'),
            'coordinates': data.get('coordinates', []),
            'directional_paths': data.get('directional_paths', {}),
            'landmarks': None,
        }
        fibers.extend(_expand_to_directional(physical))

    logger.info('Loaded %d directional fibers from JSON fallback (ClickHouse unavailable)', len(fibers))
    return fibers


class FiberListView(APIView):
    """
    GET /api/fibers — returns fiber cables with coordinates.

    Org-scoped: returns only fibers assigned to the user's organization.
    Superusers see all fibers.
    Falls back to JSON cable files when ClickHouse is unavailable.
    Each physical cable is expanded into two directional fibers.
    """
    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: FiberLineSerializer(many=True)},
        tags=['fibers'],
    )
    def get(self, request):
        cache_key = _fiber_cache_key(request.user)

        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        # Determine allowed fiber IDs
        if not request.user.is_superuser:
            fiber_ids = get_org_fiber_ids(request.user.organization)
            if not fiber_ids:
                cache.set(cache_key, [], FIBERS_CACHE_TTL)
                return Response([])
        else:
            fiber_ids = None  # no filter

        try:
            client = get_client()
        except ClickHouseUnavailableError:
            fibers = _load_fibers_from_json(fiber_ids)
            cache.set(cache_key, fibers, FIBERS_CACHE_TTL)
            return Response(fibers)

        try:
            if fiber_ids is not None:
                result = client.query(
                    """
                    SELECT
                        fiber_id,
                        fiber_name,
                        channel_coordinates,
                        color,
                        landmark_labels
                    FROM sequoia.fiber_cables
                    WHERE fiber_id IN {fids:Array(String)}
                    ORDER BY fiber_id
                    """,
                    parameters={'fids': fiber_ids},
                )
            else:
                result = client.query("""
                    SELECT
                        fiber_id,
                        fiber_name,
                        channel_coordinates,
                        color,
                        landmark_labels
                    FROM sequoia.fiber_cables
                    ORDER BY fiber_id
                """)

            fibers = []
            for row in result.named_results():
                coords = []
                for coord in row['channel_coordinates']:
                    lng, lat = coord
                    if lng is not None and lat is not None:
                        coords.append([lng, lat])
                    else:
                        coords.append([None, None])

                landmarks = []
                for idx, label in enumerate(row['landmark_labels'] or []):
                    if label:
                        landmarks.append({'channel': idx, 'name': label})

                physical = {
                    'id': row['fiber_id'],
                    'name': row['fiber_name'],
                    'color': row['color'],
                    'coordinates': coords,
                    'landmarks': landmarks if landmarks else None,
                }
                fibers.extend(_expand_to_directional(physical))

            cache.set(cache_key, fibers, FIBERS_CACHE_TTL)
            return Response(fibers)

        except Exception as e:
            logger.error('Failed to query fibers from ClickHouse: %s', e)
            fibers = _load_fibers_from_json(fiber_ids)
            cache.set(cache_key, fibers, FIBERS_CACHE_TTL)
            return Response(fibers)
