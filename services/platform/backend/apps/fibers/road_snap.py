"""
Mapbox Map Matching API client for snapping fiber coordinates to roads.

Snap once, store forever — converts raw sensor positions into road-aligned
coordinates. Results are stored as `directional_paths` on the fiber record
and served with `coordsPrecomputed=true` so the frontend uses them directly.

API limits: 100 coordinates per request, so long fibers are batched with
overlap to ensure continuity at batch boundaries.
"""

import logging
import math
import time
from pathlib import Path
from typing import Optional

import requests
import yaml

logger = logging.getLogger("sequoia.fibers")

MAPBOX_API_BASE = "https://api.mapbox.com/matching/v5/mapbox/driving"
BATCH_SIZE = 100
BATCH_OVERLAP = 5  # Overlap coordinates between batches for smooth joins
DEFAULT_RADIUS = 25  # meters — tighter than 50m to avoid parallel road matches
RATE_LIMIT_DELAY = 0.25  # seconds between API calls → 240 req/min, safe margin under Mapbox 300/min
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0  # seconds, doubles each retry


def snap_coordinates(
    coordinates: list[list[float | None]],
    access_token: str,
    profile: str = "driving",
    radius: int = DEFAULT_RADIUS,
) -> Optional[list[list[float]]]:
    """
    Snap a list of [lng, lat] coordinates to the nearest road geometry.

    Filters out null coordinates, snaps valid ones, then restores nulls
    at their original positions to preserve channel indexing.

    Returns None if the API call fails or produces unusable results.
    """
    # Build index of valid coordinates
    valid_indices: list[int] = []
    valid_coords: list[list[float]] = []
    for i, coord in enumerate(coordinates):
        if coord and coord[0] is not None and coord[1] is not None:
            valid_indices.append(i)
            valid_coords.append(coord)

    if len(valid_coords) < 2:
        logger.warning("Not enough valid coordinates to snap (%d)", len(valid_coords))
        return None

    # Snap valid coordinates in batches
    snapped_valid = _snap_batched(valid_coords, access_token, profile, radius)
    if snapped_valid is None:
        return None

    # Rebuild full coordinate array with nulls in original positions
    result: list[list[float | None]] = [[None, None] for _ in range(len(coordinates))]
    for i, orig_idx in enumerate(valid_indices):
        if i < len(snapped_valid):
            result[orig_idx] = snapped_valid[i]

    return result


def snap_directional(
    coordinates: list[list[float | None]],
    access_token: str,
    offset_meters: float = 12.0,
    radius: int = DEFAULT_RADIUS,
) -> Optional[dict[str, list[list[float | None]]]]:
    """
    Snap coordinates to roads with separate paths per direction.

    Offsets input coords laterally before snapping:
    - Direction 0: offset left (perpendicular)
    - Direction 1: offset right (perpendicular)

    Returns dict with keys '0' and '1', each containing the snapped
    coordinate array for that direction. Returns None on failure.
    """
    # Build valid coords for offset computation
    valid_coords = [c for c in coordinates if c and c[0] is not None and c[1] is not None]
    if len(valid_coords) < 2:
        logger.warning("Not enough valid coordinates for directional snap (%d)", len(valid_coords))
        return None

    results = {}
    for direction, sign in [("0", -1.0), ("1", 1.0)]:
        offset_coords = _offset_coords(coordinates, sign * offset_meters)
        snapped = snap_coordinates(offset_coords, access_token, radius=radius)
        if snapped is None:
            logger.warning("Directional snap failed for direction %s", direction)
            # Fall back to un-offset snap
            snapped = snap_coordinates(coordinates, access_token, radius=radius)
            if snapped is None:
                return None
        results[direction] = snapped

    return results


def load_snap_config(config_path: Path) -> dict:
    """
    Load and validate a per-fiber snap YAML config file.

    Returns the parsed dict. Raises ValueError on invalid config.
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError(f"Snap config must be a YAML mapping, got {type(config).__name__}")

    if "fiber_id" not in config:
        raise ValueError("Snap config missing required key: fiber_id")

    segments = config.get("segments", [])
    # Validate segments don't overlap
    covered = set()
    for seg in segments:
        ch = seg.get("channels")
        if not ch or len(ch) != 2:
            raise ValueError(f"Segment channels must be [start, end], got {ch}")
        start, end = ch
        if start > end:
            raise ValueError(f"Segment start ({start}) > end ({end})")
        for i in range(start, end + 1):
            if i in covered:
                raise ValueError(f"Overlapping segments: channel {i} appears in multiple segments")
            covered.add(i)

        for d in ["direction_0", "direction_1"]:
            if d not in seg:
                raise ValueError(f"Segment {ch} missing {d}")
            if "offset_meters" not in seg[d]:
                raise ValueError(f"Segment {ch} {d} missing offset_meters")

    return config


def snap_directional_segmented(
    coordinates: list[list[float | None]],
    access_token: str,
    config: dict,
    radius: int = DEFAULT_RADIUS,
) -> Optional[dict[str, list[list[float | None]]]]:
    """
    Snap coordinates to roads using per-segment offset configuration.

    Each segment gets its own offset pair and is snapped independently
    via separate Mapbox API calls to avoid one segment's road match
    pulling coordinates from an adjacent segment onto the wrong road.

    Returns dict with keys '0' and '1', each containing the full-length
    snapped coordinate array. Returns None on failure.
    """
    n = len(coordinates)
    default = config.get(
        "default",
        {
            "direction_0": {"offset_meters": -12},
            "direction_1": {"offset_meters": 12},
        },
    )
    segments = config.get("segments", [])

    # Build a map: channel_index -> (dir0_offset, dir1_offset)
    channel_offsets: dict[int, tuple[float, float]] = {}
    for seg in segments:
        start, end = seg["channels"]
        d0_off = seg["direction_0"]["offset_meters"]
        d1_off = seg["direction_1"]["offset_meters"]
        for i in range(start, min(end + 1, n)):
            channel_offsets[i] = (d0_off, d1_off)

    # Fill in defaults for uncovered channels
    default_d0 = default.get("direction_0", {}).get("offset_meters", -12)
    default_d1 = default.get("direction_1", {}).get("offset_meters", 12)
    for i in range(n):
        if i not in channel_offsets:
            channel_offsets[i] = (default_d0, default_d1)

    # Group consecutive channels by their offset pair
    groups: list[tuple[int, int, float, float]] = []  # (start, end, d0_off, d1_off)
    if n > 0:
        cur_start = 0
        cur_pair = channel_offsets[0]
        for i in range(1, n):
            if channel_offsets[i] != cur_pair:
                groups.append((cur_start, i - 1, cur_pair[0], cur_pair[1]))
                cur_start = i
                cur_pair = channel_offsets[i]
        groups.append((cur_start, n - 1, cur_pair[0], cur_pair[1]))

    logger.info(
        "Segmented snap: %d channels, %d groups from %d config segments",
        n,
        len(groups),
        len(segments),
    )

    # Initialize result arrays
    result_0: list[list[float | None]] = [[None, None] for _ in range(n)]
    result_1: list[list[float | None]] = [[None, None] for _ in range(n)]

    for g_idx, (g_start, g_end, d0_off, d1_off) in enumerate(groups):
        slice_coords = coordinates[g_start : g_end + 1]
        slice_len = g_end - g_start + 1

        valid_count = sum(1 for c in slice_coords if c and c[0] is not None)
        logger.info(
            "  Group %d/%d: channels %d-%d (%d channels, %d valid), "
            "offsets: dir0=%.1fm, dir1=%.1fm",
            g_idx + 1,
            len(groups),
            g_start,
            g_end,
            slice_len,
            valid_count,
            d0_off,
            d1_off,
        )

        if valid_count < 2:
            logger.warning("  Group %d: not enough valid coords, filling with nulls", g_idx + 1)
            continue

        # Snap each direction independently
        for direction, offset, result_arr in [
            ("0", d0_off, result_0),
            ("1", d1_off, result_1),
        ]:
            offset_slice = _offset_coords(slice_coords, offset)
            snapped = snap_coordinates(offset_slice, access_token, radius=radius)
            if snapped is None:
                logger.warning(
                    "  Group %d dir %s: snap failed, trying un-offset fallback",
                    g_idx + 1,
                    direction,
                )
                snapped = snap_coordinates(slice_coords, access_token, radius=radius)
                if snapped is None:
                    logger.error("  Group %d dir %s: fallback also failed", g_idx + 1, direction)
                    return None

            # Place snapped results back at correct indices
            for i, coord in enumerate(snapped):
                result_arr[g_start + i] = coord

    return {"0": result_0, "1": result_1}


def _offset_coords(
    coordinates: list[list[float | None]],
    offset_meters: float,
) -> list[list[float | None]]:
    """
    Offset coordinates perpendicular to the fiber path.

    Positive offset = right side of travel direction.
    Negative offset = left side.
    """
    result = []
    # Collect valid coords for bearing computation
    valid = [
        (i, c) for i, c in enumerate(coordinates) if c and c[0] is not None and c[1] is not None
    ]

    if len(valid) < 2:
        return list(coordinates)  # Can't compute bearing

    for i, coord in enumerate(coordinates):
        if coord is None or coord[0] is None or coord[1] is None:
            result.append([None, None])
            continue

        # Find bearing from nearby valid points
        bearing = _local_bearing(coordinates, i)
        if bearing is None:
            result.append(coord)
            continue

        # Perpendicular bearing (90 degrees clockwise)
        perp_bearing = bearing + math.pi / 2
        offset_coord = _offset_point(coord, perp_bearing, offset_meters)
        result.append(offset_coord)

    return result


def _local_bearing(coordinates: list[list[float | None]], index: int) -> Optional[float]:
    """Compute the local bearing at a given index along the coordinate list."""
    # Look for the nearest valid neighbor forward and backward
    prev = None
    for j in range(index - 1, -1, -1):
        c = coordinates[j]
        if c and c[0] is not None and c[1] is not None:
            prev = c
            break

    nxt = None
    for j in range(index + 1, len(coordinates)):
        c = coordinates[j]
        if c and c[0] is not None and c[1] is not None:
            nxt = c
            break

    if prev is None and nxt is None:
        return None

    current = coordinates[index]
    if prev is not None and nxt is not None:
        # Average of bearing from prev→current and current→next
        return _bearing(prev, nxt)
    elif nxt is not None:
        return _bearing(current, nxt)
    else:
        return _bearing(prev, current)


def _bearing(c1: list[float], c2: list[float]) -> float:
    """Compute bearing in radians from c1 to c2."""
    lng1, lat1 = math.radians(c1[0]), math.radians(c1[1])
    lng2, lat2 = math.radians(c2[0]), math.radians(c2[1])
    dlng = lng2 - lng1
    x = math.sin(dlng) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlng)
    return math.atan2(x, y)


def _offset_point(coord: list[float], bearing: float, distance_m: float) -> list[float]:
    """Move a point along a bearing by a distance in meters."""
    R = 6371000  # Earth radius
    lat1 = math.radians(coord[1])
    lng1 = math.radians(coord[0])

    lat2 = math.asin(
        math.sin(lat1) * math.cos(distance_m / R)
        + math.cos(lat1) * math.sin(distance_m / R) * math.cos(bearing)
    )
    lng2 = lng1 + math.atan2(
        math.sin(bearing) * math.sin(distance_m / R) * math.cos(lat1),
        math.cos(distance_m / R) - math.sin(lat1) * math.sin(lat2),
    )

    return [math.degrees(lng2), math.degrees(lat2)]


def _snap_batched(
    coords: list[list[float]],
    access_token: str,
    profile: str,
    radius: int = DEFAULT_RADIUS,
) -> Optional[list[list[float]]]:
    """Snap coordinates in batches of BATCH_SIZE with overlap for continuity."""
    if len(coords) <= BATCH_SIZE:
        logger.info("Batch 1/1 (coords 0-%d)", len(coords) - 1)
        return _snap_single_batch(coords, access_token, profile, radius)

    result: list[list[float]] = []
    start = 0
    step = BATCH_SIZE - BATCH_OVERLAP
    total_batches = math.ceil(max(1, len(coords) - BATCH_OVERLAP) / step)
    batch_num = 0

    while start < len(coords):
        end = min(start + BATCH_SIZE, len(coords))
        batch = coords[start:end]
        batch_num += 1

        logger.info("Batch %d/%d (coords %d-%d)", batch_num, total_batches, start, end - 1)

        snapped = _snap_single_batch(batch, access_token, profile, radius)
        if snapped is None:
            logger.error("Batch snap failed at offset %d", start)
            return None

        if start == 0:
            result.extend(snapped)
        else:
            # Skip overlap region, take only new coordinates
            result.extend(snapped[BATCH_OVERLAP:])

        start += step

    return result[: len(coords)]


def _snap_single_batch(
    coords: list[list[float]],
    access_token: str,
    profile: str,
    radius: int = DEFAULT_RADIUS,
) -> Optional[list[list[float]]]:
    """
    Call Mapbox Map Matching API for a single batch of coordinates.

    The API returns a matched geometry which may have different point density
    than the input. We project each original coordinate to the nearest point
    on the matched road polyline to preserve channel-to-position mapping.
    """
    # Build coordinate string: "lng,lat;lng,lat;..."
    coord_str = ";".join(f"{c[0]},{c[1]}" for c in coords)

    url = f"{MAPBOX_API_BASE}/{coord_str}"
    params = {
        "access_token": access_token,
        "geometries": "geojson",
        "overview": "full",
        "radiuses": ";".join([str(radius)] * len(coords)),
        "tidy": "true",
    }

    time.sleep(RATE_LIMIT_DELAY)

    data = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF * (2**attempt)
                    logger.warning(
                        "Rate limited (429), retrying in %.1fs (attempt %d/%d)",
                        wait,
                        attempt + 1,
                        MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                logger.error("Rate limited (429) after %d retries", MAX_RETRIES)
                return None
            resp.raise_for_status()
            data = resp.json()
            break
        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * (2**attempt)
                logger.warning(
                    "API request failed: %s — retrying in %.1fs (attempt %d/%d)",
                    e,
                    wait,
                    attempt + 1,
                    MAX_RETRIES,
                )
                time.sleep(wait)
                continue
            logger.error("Mapbox Map Matching API failed after %d retries: %s", MAX_RETRIES, e)
            return None

    if data is None:
        return None

    if data.get("code") != "Ok" or not data.get("matchings"):
        logger.warning("Map Matching returned no matchings: %s", data.get("code"))
        return None

    # Take the first (best) matching
    matched_coords = data["matchings"][0]["geometry"]["coordinates"]
    if len(matched_coords) < 2:
        logger.warning("Matched geometry too short (%d points)", len(matched_coords))
        return None

    # Project each original coordinate to the nearest point on the matched path
    return _project_to_path(coords, matched_coords)


def _project_to_path(
    original: list[list[float]],
    path: list[list[float]],
) -> list[list[float]]:
    """
    For each original coordinate, find the nearest point on the matched
    road polyline. This preserves the channel-to-position mapping better
    than even resampling, which distorts spacing.
    """
    result = []

    for coord in original:
        best_point = path[0]
        best_dist = float("inf")

        for i in range(len(path) - 1):
            proj = _project_point_to_segment(coord, path[i], path[i + 1])
            d = _haversine_distance(coord, proj)
            if d < best_dist:
                best_dist = d
                best_point = proj

        result.append(best_point)

    return result


def _project_point_to_segment(
    p: list[float],
    a: list[float],
    b: list[float],
) -> list[float]:
    """
    Project point p onto line segment a-b, returning the closest point
    on the segment. Uses simple linear projection in lng/lat space
    (acceptable for short segments).
    """
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    seg_len_sq = dx * dx + dy * dy

    if seg_len_sq == 0:
        return list(a)

    # Parameter t: where the projection falls on segment [0, 1]
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))

    return [a[0] + t * dx, a[1] + t * dy]


def _haversine_distance(c1: list[float], c2: list[float]) -> float:
    """Approximate distance in meters between two [lng, lat] points."""
    R = 6371000  # Earth radius in meters
    lat1, lat2 = math.radians(c1[1]), math.radians(c2[1])
    dlat = lat2 - lat1
    dlng = math.radians(c2[0] - c1[0])

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
