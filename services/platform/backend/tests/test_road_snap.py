"""
TDD tests for fiber coordinate road-snapping.

Goal: The road_snap module should:
1. Call Mapbox Map Matching API with fiber coordinates
2. Resample the matched geometry back to the original point count
3. Handle null coordinates by preserving their positions
4. Batch long fibers with overlap for continuity
5. Handle API failures gracefully (return None)
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.fibers.road_snap import (
    _haversine_distance,
    _resample_path,
    _snap_single_batch,
    snap_coordinates,
)


class TestResamplePath:
    """Pure function — no API calls needed."""

    def test_resamples_to_target_count(self):
        path = [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]
        result = _resample_path(path, 5)
        assert len(result) == 5
        # First and last should match endpoints
        assert result[0] == [0.0, 0.0]
        assert result[-1] == [2.0, 0.0]

    def test_preserves_endpoints(self):
        path = [[7.0, 43.0], [7.1, 43.1], [7.2, 43.2]]
        result = _resample_path(path, 3)
        assert result[0] == pytest.approx([7.0, 43.0], abs=1e-6)
        assert result[-1] == pytest.approx([7.2, 43.2], abs=1e-6)

    def test_single_point_target(self):
        path = [[1.0, 2.0], [3.0, 4.0]]
        result = _resample_path(path, 1)
        assert len(result) == 1
        assert result[0] == [1.0, 2.0]

    def test_more_output_than_input(self):
        path = [[0.0, 0.0], [1.0, 0.0]]
        result = _resample_path(path, 10)
        assert len(result) == 10
        # Should be evenly distributed along the line
        for i in range(10):
            assert result[i][1] == pytest.approx(0.0, abs=1e-6)


class TestHaversineDistance:
    def test_same_point_is_zero(self):
        assert _haversine_distance([7.0, 43.0], [7.0, 43.0]) == 0.0

    def test_known_distance(self):
        # ~111km per degree of latitude at equator
        d = _haversine_distance([0.0, 0.0], [0.0, 1.0])
        assert 110_000 < d < 112_000

    def test_symmetry(self):
        d1 = _haversine_distance([7.0, 43.0], [7.1, 43.1])
        d2 = _haversine_distance([7.1, 43.1], [7.0, 43.0])
        assert d1 == pytest.approx(d2, abs=0.01)


class TestSnapCoordinates:
    """Integration-level tests with mocked API."""

    @patch("apps.fibers.road_snap._snap_single_batch")
    def test_preserves_null_coordinates(self, mock_snap):
        coords = [
            [7.0, 43.0],
            [None, None],
            [7.1, 43.1],
            [7.2, 43.2],
        ]
        # Mock returns snapped version of the 3 valid coords
        mock_snap.return_value = [
            [7.001, 43.001],
            [7.101, 43.101],
            [7.201, 43.201],
        ]

        result = snap_coordinates(coords, "fake-token")

        assert result is not None
        assert len(result) == 4
        # Index 0 should be snapped
        assert result[0] == [7.001, 43.001]
        # Index 1 should remain null
        assert result[1] == [None, None]
        # Index 2 and 3 should be snapped
        assert result[2] == [7.101, 43.101]
        assert result[3] == [7.201, 43.201]

    @patch("apps.fibers.road_snap._snap_single_batch")
    def test_returns_none_on_api_failure(self, mock_snap):
        mock_snap.return_value = None
        coords = [[7.0, 43.0], [7.1, 43.1]]

        result = snap_coordinates(coords, "fake-token")
        assert result is None

    def test_returns_none_with_insufficient_coordinates(self):
        result = snap_coordinates([[7.0, 43.0]], "fake-token")
        assert result is None

    def test_returns_none_with_all_nulls(self):
        result = snap_coordinates([[None, None], [None, None]], "fake-token")
        assert result is None


class TestSnapSingleBatch:
    """Tests for the actual API interaction (mocked)."""

    @patch("apps.fibers.road_snap.requests.get")
    def test_successful_snap(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "Ok",
            "matchings": [
                {"geometry": {"coordinates": [[7.001, 43.001], [7.051, 43.051], [7.101, 43.101]]}}
            ],
        }
        mock_get.return_value = mock_response

        result = _snap_single_batch(
            [[7.0, 43.0], [7.05, 43.05], [7.1, 43.1]],
            "fake-token",
            "driving",
        )

        assert result is not None
        assert len(result) == 3  # Same count as input

    @patch("apps.fibers.road_snap.requests.get")
    def test_api_error_returns_none(self, mock_get):
        import requests as req

        mock_get.side_effect = req.ConnectionError("Network error")

        result = _snap_single_batch(
            [[7.0, 43.0], [7.1, 43.1]],
            "fake-token",
            "driving",
        )
        assert result is None

    @patch("apps.fibers.road_snap.requests.get")
    def test_no_matchings_returns_none(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": "NoMatch", "matchings": []}
        mock_get.return_value = mock_response

        result = _snap_single_batch(
            [[7.0, 43.0], [7.1, 43.1]],
            "fake-token",
            "driving",
        )
        assert result is None
