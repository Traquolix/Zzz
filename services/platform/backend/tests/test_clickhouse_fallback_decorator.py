"""
Tests for the clickhouse_fallback view decorator.

Verifies:
1. Normal responses pass through unchanged
2. ClickHouseUnavailableError → 503 when no fallback
3. ClickHouseUnavailableError → fallback result when fallback provided
4. Fallback failure → 503
"""

from unittest.mock import MagicMock

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.shared.clickhouse import clickhouse_fallback
from apps.shared.exceptions import ClickHouseUnavailableError


def _make_request(method='GET', path='/api/test'):
    req = MagicMock()
    req.method = method
    req.path = path
    return req


class TestClickHouseFallbackDecorator:

    def test_success_passes_through(self):
        """Normal response is returned unchanged."""
        class View(APIView):
            @clickhouse_fallback()
            def get(self, request):
                return Response({'data': [1, 2, 3]})

        view = View()
        resp = view.get(_make_request())
        assert resp.status_code == 200
        assert resp.data == {'data': [1, 2, 3]}

    def test_no_fallback_returns_503(self):
        """Without fallback_fn, ClickHouseUnavailableError → 503."""
        class View(APIView):
            @clickhouse_fallback()
            def get(self, request):
                raise ClickHouseUnavailableError('down')

        view = View()
        resp = view.get(_make_request())
        assert resp.status_code == 503
        assert resp.data['code'] == 'analytics_unavailable'

    def test_with_fallback_returns_fallback_result(self):
        """With fallback_fn, ClickHouseUnavailableError → fallback response."""
        def my_fallback(self, request, *args, **kwargs):
            return Response({'data': [], 'fallback': True})

        class View(APIView):
            @clickhouse_fallback(fallback_fn=my_fallback)
            def get(self, request):
                raise ClickHouseUnavailableError('down')

        view = View()
        resp = view.get(_make_request())
        assert resp.status_code == 200
        assert resp.data['fallback'] is True

    def test_fallback_failure_returns_503(self):
        """When fallback_fn also raises, returns 503."""
        def bad_fallback(self, request, *args, **kwargs):
            raise RuntimeError('fallback also broken')

        class View(APIView):
            @clickhouse_fallback(fallback_fn=bad_fallback)
            def get(self, request):
                raise ClickHouseUnavailableError('down')

        view = View()
        resp = view.get(_make_request())
        assert resp.status_code == 503
        assert resp.data['code'] == 'analytics_unavailable'

    def test_non_clickhouse_errors_propagate(self):
        """Non-ClickHouse errors are not caught by the decorator."""
        class View(APIView):
            @clickhouse_fallback()
            def get(self, request):
                raise ValueError('unrelated error')

        view = View()
        try:
            view.get(_make_request())
            assert False, 'Should have raised ValueError'
        except ValueError:
            pass
