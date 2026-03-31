"""
SHM (Structural Health Monitoring) views — spectral data, peaks, summary, and status.

All queries are org-scoped via Infrastructure.organization FK.
"""

import logging

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.monitoring.serializers import (
    SpectralDataSerializer,
    SpectralPeaksSerializer,
)
from apps.monitoring.view_helpers import _verify_infrastructure_access
from apps.shared.permissions import IsActiveUser

logger = logging.getLogger("sequoia.monitoring.views")


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
            OpenApiParameter(
                name="infrastructureId",
                type=str,
                description="Infrastructure ID for real-time data",
            ),
            OpenApiParameter(name="maxTimeSamples", type=int, description="Max time samples"),
            OpenApiParameter(name="maxFreqBins", type=int, description="Max frequency bins"),
            OpenApiParameter(name="startIdx", type=int, description="Start time index"),
            OpenApiParameter(name="endIdx", type=int, description="End time index"),
            OpenApiParameter(name="startTime", type=str, description="Start time (ISO format)"),
            OpenApiParameter(name="endTime", type=str, description="End time (ISO format)"),
        ],
        responses={200: SpectralDataSerializer},
        tags=["shm"],
    )
    def get(self, request: Request) -> Response:
        from datetime import datetime

        import numpy as np

        from apps.monitoring.hdf5_reader import load_spectral_data, sample_file_exists

        # Org-scoping: validate infrastructure access if specified
        error_resp = _verify_infrastructure_access(
            request.user,
            request.query_params.get("infrastructureId"),
        )
        if error_resp:
            return error_resp

        # Demo mode: return sample data from HDF5 file
        if not sample_file_exists():
            return Response(
                {"detail": "No SHM sample data available", "code": "shm_data_unavailable"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            data = load_spectral_data()
        except (OSError, KeyError, ValueError) as e:
            logger.error("Failed to load spectral data: %s", e)
            return Response(
                {"detail": "Failed to load spectral data", "code": "shm_load_error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Apply time filtering if startTime/endTime provided (takes priority over indices)
        start_time_str = request.query_params.get("startTime")
        end_time_str = request.query_params.get("endTime")

        if start_time_str or end_time_str:
            # Calculate absolute timestamps for all samples
            timestamps = data.t0.timestamp() + data.dt

            # Parse filter times
            start_ts = (
                datetime.fromisoformat(start_time_str.replace("Z", "+00:00")).timestamp()
                if start_time_str
                else 0
            )
            end_ts = (
                datetime.fromisoformat(end_time_str.replace("Z", "+00:00")).timestamp()
                if end_time_str
                else float("inf")
            )

            # Find indices within the time range
            mask = (timestamps >= start_ts) & (timestamps <= end_ts)
            indices = np.where(mask)[0]

            if len(indices) > 0:
                start_idx = int(indices[0])
                end_idx = int(indices[-1]) + 1
                data = data.slice_time(start_idx, end_idx)
        else:
            # Apply index-based time slicing if requested
            start_idx = request.query_params.get("startIdx")
            end_idx = request.query_params.get("endIdx")
            if start_idx is not None or end_idx is not None:
                start = int(start_idx) if start_idx else 0
                end = int(end_idx) if end_idx else data.num_time_samples
                data = data.slice_time(start, end)

        # Apply downsampling (clamped to prevent unbounded allocation)
        max_time = min(int(request.query_params.get("maxTimeSamples", 500)), 5000)
        max_freq = min(int(request.query_params.get("maxFreqBins", 200)), 2000)

        data = data.downsample_time(max_time)
        data = data.downsample_freq(max_freq)

        return Response(data.to_dict(log_scale=True))


class SpectralPeaksView(APIView):
    """
    GET /api/shm/peaks — returns peak frequencies over time for scatter plot.

    Query parameters:
    - infrastructureId: Infrastructure ID (optional, for production real-time data)
    - maxSamples: Maximum number of time samples to return (optional, cap 10000)
    - startTime: ISO timestamp for start of time range (optional)
    - endTime: ISO timestamp for end of time range (optional)

    In demo mode (no infrastructureId), returns sample data from HDF5 file.
    In production mode, will fetch real-time data for the specified infrastructure.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="infrastructureId",
                type=str,
                description="Infrastructure ID for real-time data",
            ),
            OpenApiParameter(name="maxSamples", type=int, description="Max samples"),
            OpenApiParameter(name="startTime", type=str, description="Start time (ISO format)"),
            OpenApiParameter(name="endTime", type=str, description="End time (ISO format)"),
        ],
        responses={200: SpectralPeaksSerializer},
        tags=["shm"],
    )
    def get(self, request: Request) -> Response:
        from datetime import datetime, timedelta

        import numpy as np

        from apps.monitoring.hdf5_reader import (
            load_peak_frequencies,
            load_spectral_data,
            sample_file_exists,
        )

        # Org-scoping: validate infrastructure access if specified
        error_resp = _verify_infrastructure_access(
            request.user,
            request.query_params.get("infrastructureId"),
        )
        if error_resp:
            return error_resp

        # Demo mode: return sample data from HDF5 file
        if not sample_file_exists():
            return Response(
                {"detail": "No SHM sample data available", "code": "shm_data_unavailable"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            data = load_spectral_data()
            # Use cached peak frequencies instead of recomputing find_peaks
            all_peak_freqs, all_peak_powers = load_peak_frequencies()
        except (OSError, KeyError, ValueError) as e:
            logger.error("Failed to load spectral data: %s", e)
            return Response(
                {"detail": "Failed to load spectral data", "code": "shm_load_error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Defensive copies: cached arrays are process-global and must not be
        # mutated in-place. Subsequent basic slices (e.g. arr[si:ei]) produce
        # views into these copies — safe because the copies isolate us from
        # the cache, and we do no in-place mutation after slicing.
        dt = data.dt.copy()
        peak_freqs = all_peak_freqs.copy()
        peak_powers = all_peak_powers.copy()
        t0 = data.t0

        # Apply time filtering. When no startTime/endTime and no maxSamples
        # are provided, default to the last day of available data so the
        # endpoint never returns the full unfiltered dataset by accident.
        start_time_str = request.query_params.get("startTime")
        end_time_str = request.query_params.get("endTime")
        max_samples_param = request.query_params.get("maxSamples")

        try:
            max_samples_int = int(max_samples_param) if max_samples_param is not None else None
        except (ValueError, TypeError):
            max_samples_int = None

        if (
            not start_time_str
            and not end_time_str
            and (max_samples_int is None or max_samples_int <= 0)
        ):
            # Use the file's own end time so this works for both live and
            # historical/demo data (where "today" may not overlap the file).
            last_offset = float(dt[-1])
            file_end = t0 + timedelta(seconds=last_offset)
            day_start = file_end.replace(hour=0, minute=0, second=0, microsecond=0)
            start_time_str = day_start.isoformat()
            end_time_str = (day_start + timedelta(days=1)).isoformat()

        if start_time_str or end_time_str:
            timestamps = t0.timestamp() + dt

            start_ts = (
                datetime.fromisoformat(start_time_str.replace("Z", "+00:00")).timestamp()
                if start_time_str
                else 0
            )
            end_ts = (
                datetime.fromisoformat(end_time_str.replace("Z", "+00:00")).timestamp()
                if end_time_str
                else float("inf")
            )

            mask = (timestamps >= start_ts) & (timestamps <= end_ts)
            idx = np.where(mask)[0]

            if len(idx) > 0:
                si, ei = int(idx[0]), int(idx[-1]) + 1
                start_offset = float(dt[si])
                dt = dt[si:ei] - dt[si]
                peak_freqs = peak_freqs[si:ei]
                peak_powers = peak_powers[si:ei]
                t0 = t0 + timedelta(seconds=start_offset)

        # Downsample by selecting evenly-spaced indices.
        # When the caller passes an explicit maxSamples we honour it (capped at 10 000).
        # Otherwise we skip downsampling — the time filter already bounds the result.
        max_samples = (
            min(max_samples_int, 10000)
            if max_samples_int is not None and max_samples_int > 0
            else 0
        )

        n = len(dt)
        if max_samples > 0 and max_samples < n:
            sel = np.linspace(0, n - 1, max_samples, dtype=int)
            dt = dt[sel]
            peak_freqs = peak_freqs[sel]
            peak_powers = peak_powers[sel]

        return Response(
            {
                "t0": t0.isoformat(),
                "dt": dt.tolist(),
                "peakFrequencies": peak_freqs.tolist(),
                "peakPowers": peak_powers.tolist(),
                "freqRange": list(data.freq_range),
            }
        )


class SpectralSummaryView(APIView):
    """
    GET /api/shm/summary — returns summary info about available spectral data.

    Query parameters:
    - infrastructureId: Infrastructure ID (optional, for production real-time data)

    Lightweight endpoint to check data availability without loading full dataset.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="infrastructureId",
                type=str,
                description="Infrastructure ID for real-time data",
            ),
        ],
        tags=["shm"],
    )
    def get(self, request: Request) -> Response:
        from apps.monitoring.hdf5_reader import get_spectral_summary, sample_file_exists

        # Org-scoping: validate infrastructure access if specified
        error_resp = _verify_infrastructure_access(
            request.user,
            request.query_params.get("infrastructureId"),
        )
        if error_resp:
            return error_resp

        if not sample_file_exists():
            return Response(
                {"detail": "No SHM sample data available", "code": "shm_data_unavailable"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            summary = get_spectral_summary()
        except (OSError, KeyError, ValueError) as e:
            logger.error("Failed to get spectral summary: %s", e)
            return Response(
                {"detail": "Failed to load spectral data", "code": "shm_load_error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(summary)


class SHMStatusView(APIView):
    """
    GET /api/monitoring/shm/status/<infrastructure_id> — compute live SHM status.

    Uses the SHM intelligence module to detect frequency shifts and classify
    deviation severity. For demo, generates plausible frequency data.
    """

    permission_classes = [IsActiveUser]

    @extend_schema(
        responses={200: dict},
        tags=["shm"],
    )
    def get(self, request: Request, infrastructure_id: str) -> Response:
        import random

        import numpy as np

        from apps.monitoring.shm_intelligence import (
            compute_baseline,
            detect_frequency_shift,
        )

        # Org-scoping: verify infrastructure belongs to user's org
        error_resp = _verify_infrastructure_access(request.user, infrastructure_id)
        if error_resp:
            return error_resp

        # Seed RNG with infrastructure_id for deterministic demo responses
        rng = random.Random(infrastructure_id)

        # Simulate baseline frequencies (would come from ClickHouse in production)
        baseline_freqs = np.array([1.10 + rng.gauss(0, 0.02) for _ in range(20)])
        baseline = compute_baseline(baseline_freqs)

        if baseline is None:
            return Response(
                {"detail": "Insufficient baseline data", "code": "insufficient_data"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Simulate current frequencies
        current_freqs = np.array([1.12 + rng.gauss(0, 0.03) for _ in range(10)])

        shift = detect_frequency_shift(baseline, current_freqs)

        # Map SHM classification to frontend status
        status_map = {
            "normal": "nominal",
            "warning": "warning",
            "alert": "warning",
            "critical": "critical",
        }

        return Response(
            {
                "status": status_map.get(shift.severity, "nominal"),
                "currentMean": round(shift.current_mean, 4),
                "baselineMean": round(shift.baseline_mean, 4),
                "deviationSigma": round(shift.deviation_sigma, 2),
                "direction": shift.direction,
                "severity": shift.severity,
            }
        )
