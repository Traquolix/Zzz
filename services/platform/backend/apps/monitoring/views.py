"""
Monitoring views — incidents (ClickHouse), infrastructure (PostgreSQL), stats, SHM spectra.

All ClickHouse queries are org-scoped via FiberAssignment: non-superusers
only see data from fibers assigned to their organization.
"""

import logging
import time

_PROCESS_START_TIME = time.time()

from django.core.cache import cache as django_cache
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.response import Response
from rest_framework.views import APIView

from django.conf import settings

from apps.fibers.utils import get_org_fiber_ids
from apps.monitoring.models import Infrastructure
from apps.monitoring.serializers import (
    IncidentSerializer,
    IncidentSnapshotSerializer,
    InfrastructureSerializer,
    StatsSerializer,
)
from apps.shared.clickhouse import query, query_scalar
from apps.shared.exceptions import ClickHouseUnavailableError
from apps.shared.permissions import IsActiveUser

logger = logging.getLogger('sequoia')

INCIDENTS_CACHE_TTL = 10  # 10 seconds
STATS_CACHE_TTL = 5  # 5 seconds
FALLBACK_CACHE_TTL = 60  # 60 seconds when ClickHouse unavailable (reduce log spam)


def _get_fiber_ids_or_none(user):
    """Return fiber_ids list for org-scoped users, None for superusers."""
    if user.is_superuser:
        return None
    return get_org_fiber_ids(user.organization)


def _incidents_cache_key(user):
    if user.is_superuser:
        return 'incidents:all'
    return f'incidents:org:{user.organization_id}'


def _stats_cache_key(user):
    if user.is_superuser:
        return 'stats:all'
    return f'stats:org:{user.organization_id}'


class IncidentListView(APIView):
    """
    GET /api/incidents — returns active + recent incidents from ClickHouse.

    Org-scoped: only incidents from the user's assigned fibers.
    """
    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: IncidentSerializer(many=True)},
        tags=['incidents'],
    )
    def get(self, request):
        cache_key = _incidents_cache_key(request.user)
        cached = django_cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        fiber_ids = _get_fiber_ids_or_none(request.user)
        if fiber_ids is not None and not fiber_ids:
            django_cache.set(cache_key, [], INCIDENTS_CACHE_TTL)
            return Response([])

        try:
            if fiber_ids is not None:
                rows = query(
                    """
                    SELECT
                        incident_id, incident_type, severity,
                        fiber_id, channel_start, timestamp,
                        status, duration_seconds
                    FROM sequoia.fiber_incidents
                    WHERE timestamp >= now() - INTERVAL 24 HOUR
                      AND fiber_id IN {fids:Array(String)}
                    ORDER BY timestamp DESC
                    LIMIT 500
                    """,
                    parameters={'fids': fiber_ids},
                )
            else:
                rows = query("""
                    SELECT
                        incident_id, incident_type, severity,
                        fiber_id, channel_start, timestamp,
                        status, duration_seconds
                    FROM sequoia.fiber_incidents
                    WHERE timestamp >= now() - INTERVAL 24 HOUR
                    ORDER BY timestamp DESC
                    LIMIT 500
                """)
        except ClickHouseUnavailableError:
            # Fallback to simulation incidents if available
            try:
                from apps.realtime.simulation import get_simulation_incidents
                sim_incidents = get_simulation_incidents()
                if sim_incidents:
                    django_cache.set(cache_key, sim_incidents, FALLBACK_CACHE_TTL)
                    return Response(sim_incidents)
            except ImportError:
                pass
            django_cache.set(cache_key, [], FALLBACK_CACHE_TTL)
            return Response([])

        incidents = []
        for row in rows:
            incidents.append({
                'id': row['incident_id'],
                'type': row['incident_type'],
                'severity': row['severity'],
                'fiberLine': row['fiber_id'],
                'channel': row['channel_start'],
                'detectedAt': row['timestamp'].isoformat() if hasattr(row['timestamp'], 'isoformat') else str(row['timestamp']),
                'status': row['status'],
                'duration': row['duration_seconds'] * 1000 if row['duration_seconds'] else None,
            })

        django_cache.set(cache_key, incidents, INCIDENTS_CACHE_TTL)
        return Response(incidents)


class IncidentSnapshotView(APIView):
    """
    GET /api/incidents/<id>/snapshot — high-res speed data around an incident.

    Org-scoped: verifies the incident's fiber belongs to the user's org.

    Note: snapshots are empty in simulation mode because the simulation engine
    does not write to the speed_hires ClickHouse table. Snapshots require live
    pipeline data flowing through Kafka -> ClickHouse.
    """
    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: IncidentSnapshotSerializer},
        tags=['incidents'],
    )
    def get(self, request, incident_id):
        try:
            incident_rows = query(
                """
                SELECT fiber_id, channel_start, channel_end, timestamp_ns
                FROM sequoia.fiber_incidents
                WHERE incident_id = {id:String}
                LIMIT 1
                """,
                parameters={'id': incident_id},
            )
        except ClickHouseUnavailableError:
            return Response({'detail': 'ClickHouse unavailable', 'code': 'clickhouse_unavailable'}, status=503)

        if not incident_rows:
            return Response({'detail': 'Incident not found', 'code': 'incident_not_found'}, status=404)

        incident = incident_rows[0]
        fiber_id = incident['fiber_id']

        # Org-scoping: verify the incident's fiber belongs to user's org
        fiber_ids = _get_fiber_ids_or_none(request.user)
        if fiber_ids is not None and fiber_id not in fiber_ids:
            return Response({'detail': 'Incident not found', 'code': 'incident_not_found'}, status=404)

        center_ch = (incident['channel_start'] + incident['channel_end']) // 2
        ts_ns = incident['timestamp_ns']

        try:
            speed_rows = query(
                """
                SELECT
                    fiber_id, ch, speed, toUnixTimestamp64Milli(ts) AS timestamp
                FROM sequoia.speed_hires
                WHERE fiber_id = {fid:String}
                  AND ch BETWEEN {ch_min:UInt16} AND {ch_max:UInt16}
                  AND ts BETWEEN fromUnixTimestamp64Nano({ts_start:UInt64})
                              AND fromUnixTimestamp64Nano({ts_end:UInt64})
                ORDER BY ts
                LIMIT 10000
                """,
                parameters={
                    'fid': fiber_id,
                    'ch_min': max(0, center_ch - 50),
                    'ch_max': center_ch + 50,
                    'ts_start': ts_ns - 60_000_000_000,
                    'ts_end': ts_ns + 60_000_000_000,
                },
            )
        except ClickHouseUnavailableError:
            return Response({'detail': 'ClickHouse unavailable', 'code': 'clickhouse_unavailable'}, status=503)

        detections = []
        for row in speed_rows:
            speed = row['speed']
            detections.append({
                'fiberLine': row['fiber_id'],
                'channel': row['ch'],
                'speed': abs(speed),
                'count': 1,
                'direction': 0 if speed >= 0 else 1,
                'timestamp': row['timestamp'],
            })

        return Response({
            'incidentId': incident_id,
            'fiberLine': fiber_id,
            'centerChannel': center_ch,
            'capturedAt': int(time.time() * 1000),
            'detections': detections,
        })


class InfrastructureListView(APIView):
    """
    GET /api/infrastructure — returns infrastructure items from PostgreSQL.

    Already org-scoped via Organization FK.
    """
    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: InfrastructureSerializer(many=True)},
        tags=['infrastructure'],
    )
    def get(self, request):
        qs = Infrastructure.objects.all()
        if hasattr(request.user, 'organization') and request.user.organization:
            qs = qs.filter(organization=request.user.organization)

        data = []
        for item in qs:
            image_url = None
            if item.image:
                image_url = request.build_absolute_uri(f'/media/infrastructure/{item.image}')
            data.append({
                'id': item.id,
                'type': item.type,
                'name': item.name,
                'fiberId': item.fiber_id,
                'startChannel': item.start_channel,
                'endChannel': item.end_channel,
                'imageUrl': image_url,
            })
        return Response(data)


class StatsView(APIView):
    """
    GET /api/stats — system-level statistics.

    Org-scoped: counts only fibers/channels/incidents/detections from
    the user's assigned fibers.
    """
    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: StatsSerializer},
        tags=['stats'],
    )
    def get(self, request):
        cache_key = _stats_cache_key(request.user)
        cached = django_cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        fiber_ids = _get_fiber_ids_or_none(request.user)

        try:
            if fiber_ids is not None:
                if not fiber_ids:
                    fiber_count = 0
                    total_channels = 0
                    active_incidents = 0
                    recent_rows = 0
                    active_vehicles = 0
                else:
                    fiber_count = query_scalar(
                        "SELECT count(DISTINCT fiber_id) FROM sequoia.fiber_cables WHERE fiber_id IN {fids:Array(String)}",
                        parameters={'fids': fiber_ids},
                    ) or 0

                    total_channels = query_scalar(
                        "SELECT sum(length(channel_coordinates)) FROM sequoia.fiber_cables WHERE fiber_id IN {fids:Array(String)}",
                        parameters={'fids': fiber_ids},
                    ) or 0

                    active_incidents = query_scalar(
                        "SELECT count() FROM sequoia.fiber_incidents WHERE status = 'active' AND fiber_id IN {fids:Array(String)}",
                        parameters={'fids': fiber_ids},
                    ) or 0

                    recent_rows = query_scalar(
                        """
                        SELECT count() / 10
                        FROM sequoia.speed_hires
                        WHERE ts >= now() - INTERVAL 10 SECOND
                          AND fiber_id IN {fids:Array(String)}
                        """,
                        parameters={'fids': fiber_ids},
                    ) or 0

                    active_vehicles = query_scalar(
                        """
                        SELECT coalesce(sum(count), 0)
                        FROM sequoia.count_hires
                        WHERE ts >= (now() - toIntervalSecond(30))
                          AND fiber_id IN {fids:Array(String)}
                        """,
                        parameters={'fids': fiber_ids},
                    ) or 0
            else:
                fiber_count = query_scalar(
                    "SELECT count(DISTINCT fiber_id) FROM sequoia.fiber_cables"
                ) or 0

                total_channels = query_scalar(
                    "SELECT sum(length(channel_coordinates)) FROM sequoia.fiber_cables"
                ) or 0

                active_incidents = query_scalar(
                    "SELECT count() FROM sequoia.fiber_incidents WHERE status = 'active'"
                ) or 0

                recent_rows = query_scalar("""
                    SELECT count() / 10
                    FROM sequoia.speed_hires
                    WHERE ts >= now() - INTERVAL 10 SECOND
                """) or 0

                active_vehicles = query_scalar("""
                    SELECT coalesce(sum(count), 0)
                    FROM sequoia.count_hires
                    WHERE ts >= (now() - toIntervalSecond(30))
                """) or 0

        except ClickHouseUnavailableError:
            fiber_count = 0
            total_channels = 0
            active_incidents = 0
            recent_rows = 0
            active_vehicles = 0

        # Use longer cache when ClickHouse is unavailable to reduce retry spam
        is_fallback = (fiber_count == 0 and total_channels == 0)
        cache_ttl = FALLBACK_CACHE_TTL if is_fallback else STATS_CACHE_TTL

        data = {
            'fiberCount': fiber_count,
            'totalChannels': total_channels,
            'activeVehicles': int(active_vehicles),
            'detectionsPerSecond': round(float(recent_rows), 1),
            'activeIncidents': active_incidents,
            'systemUptime': int(time.time() - _PROCESS_START_TIME),
        }
        django_cache.set(cache_key, data, cache_ttl)
        return Response(data)


class SpectralDataView(APIView):
    """
    GET /api/shm/spectra — returns spectral data for SHM heatmap visualization.

    Query parameters:
    - infrastructureId: Infrastructure ID (optional, for production real-time data)
    - maxTimeSamples: Maximum number of time samples to return (default 500)
    - maxFreqBins: Maximum number of frequency bins to return (default 200)
    - startIdx: Starting time index for slicing (optional)
    - endIdx: Ending time index for slicing (optional)
    - startTime: ISO timestamp for start of time range (optional)
    - endTime: ISO timestamp for end of time range (optional)

    In demo mode (no infrastructureId), returns sample data from HDF5 file.
    In production mode, will fetch real-time data for the specified infrastructure.
    """
    permission_classes = [IsActiveUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='infrastructureId', type=str, description='Infrastructure ID for real-time data'),
            OpenApiParameter(name='maxTimeSamples', type=int, description='Max time samples'),
            OpenApiParameter(name='maxFreqBins', type=int, description='Max frequency bins'),
            OpenApiParameter(name='startIdx', type=int, description='Start time index'),
            OpenApiParameter(name='endIdx', type=int, description='End time index'),
            OpenApiParameter(name='startTime', type=str, description='Start time (ISO format)'),
            OpenApiParameter(name='endTime', type=str, description='End time (ISO format)'),
        ],
        tags=['shm'],
    )
    def get(self, request):
        from datetime import datetime
        import numpy as np
        from apps.monitoring.hdf5_reader import load_spectral_data, sample_file_exists

        # TODO: In production, use infrastructureId to fetch real-time data
        # infrastructure_id = request.query_params.get('infrastructureId')
        # if infrastructure_id:
        #     return self._get_realtime_data(infrastructure_id, request)

        # Demo mode: return sample data from HDF5 file
        if not sample_file_exists():
            return Response(
                {'detail': 'No SHM sample data available', 'code': 'shm_data_unavailable'},
                status=404
            )

        try:
            data = load_spectral_data()
        except Exception as e:
            logger.error(f"Failed to load spectral data: {e}")
            return Response(
                {'detail': 'Failed to load spectral data', 'code': 'shm_load_error'},
                status=500
            )

        # Apply time filtering if startTime/endTime provided (takes priority over indices)
        start_time_str = request.query_params.get('startTime')
        end_time_str = request.query_params.get('endTime')

        if start_time_str or end_time_str:
            # Calculate absolute timestamps for all samples
            timestamps = np.array([
                data.t0.timestamp() + offset for offset in data.dt
            ])

            # Parse filter times
            start_ts = datetime.fromisoformat(start_time_str.replace('Z', '+00:00')).timestamp() if start_time_str else 0
            end_ts = datetime.fromisoformat(end_time_str.replace('Z', '+00:00')).timestamp() if end_time_str else float('inf')

            # Find indices within the time range
            mask = (timestamps >= start_ts) & (timestamps <= end_ts)
            indices = np.where(mask)[0]

            if len(indices) > 0:
                start_idx = int(indices[0])
                end_idx = int(indices[-1]) + 1
                data = data.slice_time(start_idx, end_idx)
        else:
            # Apply index-based time slicing if requested
            start_idx = request.query_params.get('startIdx')
            end_idx = request.query_params.get('endIdx')
            if start_idx is not None or end_idx is not None:
                start = int(start_idx) if start_idx else 0
                end = int(end_idx) if end_idx else data.num_time_samples
                data = data.slice_time(start, end)

        # Apply downsampling
        max_time = int(request.query_params.get('maxTimeSamples', 500))
        max_freq = int(request.query_params.get('maxFreqBins', 200))

        data = data.downsample_time(max_time)
        data = data.downsample_freq(max_freq)

        return Response(data.to_dict(log_scale=True))


class SpectralPeaksView(APIView):
    """
    GET /api/shm/peaks — returns peak frequencies over time for scatter plot.

    Query parameters:
    - infrastructureId: Infrastructure ID (optional, for production real-time data)
    - maxSamples: Maximum number of time samples to return (default 1000)
    - startTime: ISO timestamp for start of time range (optional)
    - endTime: ISO timestamp for end of time range (optional)

    In demo mode (no infrastructureId), returns sample data from HDF5 file.
    In production mode, will fetch real-time data for the specified infrastructure.
    """
    permission_classes = [IsActiveUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(name='infrastructureId', type=str, description='Infrastructure ID for real-time data'),
            OpenApiParameter(name='maxSamples', type=int, description='Max samples'),
            OpenApiParameter(name='startTime', type=str, description='Start time (ISO format)'),
            OpenApiParameter(name='endTime', type=str, description='End time (ISO format)'),
        ],
        tags=['shm'],
    )
    def get(self, request):
        from datetime import datetime
        import numpy as np
        from apps.monitoring.hdf5_reader import load_spectral_data, sample_file_exists

        # TODO: In production, use infrastructureId to fetch real-time data
        # infrastructure_id = request.query_params.get('infrastructureId')
        # if infrastructure_id:
        #     return self._get_realtime_peaks(infrastructure_id, request)

        # Demo mode: return sample data from HDF5 file
        if not sample_file_exists():
            return Response(
                {'detail': 'No SHM sample data available', 'code': 'shm_data_unavailable'},
                status=404
            )

        try:
            data = load_spectral_data()
        except Exception as e:
            logger.error(f"Failed to load spectral data: {e}")
            return Response(
                {'detail': 'Failed to load spectral data', 'code': 'shm_load_error'},
                status=500
            )

        # Apply time filtering if startTime/endTime provided
        start_time_str = request.query_params.get('startTime')
        end_time_str = request.query_params.get('endTime')

        if start_time_str or end_time_str:
            # Calculate absolute timestamps for all samples
            timestamps = np.array([
                data.t0.timestamp() + offset for offset in data.dt
            ])

            # Parse filter times
            start_ts = datetime.fromisoformat(start_time_str.replace('Z', '+00:00')).timestamp() if start_time_str else 0
            end_ts = datetime.fromisoformat(end_time_str.replace('Z', '+00:00')).timestamp() if end_time_str else float('inf')

            # Find indices within the time range
            mask = (timestamps >= start_ts) & (timestamps <= end_ts)
            indices = np.where(mask)[0]

            if len(indices) > 0:
                start_idx = int(indices[0])
                end_idx = int(indices[-1]) + 1
                data = data.slice_time(start_idx, end_idx)

        max_samples = int(request.query_params.get('maxSamples', 1000))
        data = data.downsample_time(max_samples)

        peak_freqs, peak_powers = data.get_peak_frequencies()

        return Response({
            't0': data.t0.isoformat(),
            'dt': data.dt.tolist(),
            'peakFrequencies': peak_freqs.tolist(),
            'peakPowers': peak_powers.tolist(),
            'freqRange': list(data.freq_range),
        })


class SpectralSummaryView(APIView):
    """
    GET /api/shm/summary — returns summary info about available spectral data.

    Lightweight endpoint to check data availability without loading full dataset.
    """
    permission_classes = [IsActiveUser]

    @extend_schema(tags=['shm'])
    def get(self, request):
        from apps.monitoring.hdf5_reader import get_spectral_summary, sample_file_exists

        if not sample_file_exists():
            return Response(
                {'detail': 'No SHM sample data available', 'code': 'shm_data_unavailable'},
                status=404
            )

        try:
            summary = get_spectral_summary()
        except Exception as e:
            logger.error(f"Failed to get spectral summary: {e}")
            return Response(
                {'detail': 'Failed to load spectral data', 'code': 'shm_load_error'},
                status=500
            )

        return Response(summary)
