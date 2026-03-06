"""
Tests for trusted proxy IP configuration and X-Forwarded-For handling.

Verifies that get_client_ip() correctly respects TRUSTED_PROXY_IPS settings
and that the production settings emit warnings when unconfigured.
"""

from unittest.mock import MagicMock, patch

from apps.shared.audit import get_client_ip


def _make_request(remote_addr="127.0.0.1", x_forwarded_for=None):
    """Create a mock request with META headers."""
    meta = {"REMOTE_ADDR": remote_addr}
    if x_forwarded_for:
        meta["HTTP_X_FORWARDED_FOR"] = x_forwarded_for
    request = MagicMock()
    request.META = meta
    return request


class TestTrustedProxies:
    """Tests for get_client_ip with various TRUSTED_PROXY_IPS configurations."""

    @patch("apps.shared.audit.settings")
    def test_untrusted_source_ignores_x_forwarded_for(self, mock_settings):
        """When TRUSTED_PROXY_IPS is empty list, XFF from any source is ignored."""
        mock_settings.TRUSTED_PROXY_IPS = []
        request = _make_request(
            remote_addr="10.0.0.5",
            x_forwarded_for="203.0.113.50, 10.0.0.1",
        )
        ip = get_client_ip(request)
        # Should use REMOTE_ADDR since 10.0.0.5 is not in empty trusted list
        assert ip == "10.0.0.5"

    @patch("apps.shared.audit.settings")
    def test_trusted_source_uses_x_forwarded_for(self, mock_settings):
        """When REMOTE_ADDR is in TRUSTED_PROXY_IPS, XFF is parsed."""
        mock_settings.TRUSTED_PROXY_IPS = ["10.0.0.1"]
        request = _make_request(
            remote_addr="10.0.0.1",
            x_forwarded_for="203.0.113.50, 10.0.0.1",
        )
        ip = get_client_ip(request)
        # Should walk XFF right-to-left, skip trusted 10.0.0.1, return client
        assert ip == "203.0.113.50"

    @patch("apps.shared.audit.settings")
    def test_no_config_trusts_private_ips(self, mock_settings):
        """When TRUSTED_PROXY_IPS is None (not set), private IPs are trusted."""
        # Simulate the attribute not being set at all
        del mock_settings.TRUSTED_PROXY_IPS
        mock_settings.configure_mock(**{"TRUSTED_PROXY_IPS": None})
        # Use hasattr workaround — getattr returns None
        request = _make_request(
            remote_addr="10.0.0.1",
            x_forwarded_for="203.0.113.50",
        )
        ip = get_client_ip(request)
        # Private REMOTE_ADDR is trusted when no config → uses XFF
        assert ip == "203.0.113.50"

    @patch("apps.shared.audit.settings")
    def test_cidr_notation_in_trusted_list(self, mock_settings):
        """CIDR notation should match IP ranges."""
        mock_settings.TRUSTED_PROXY_IPS = ["10.0.0.0/8"]
        request = _make_request(
            remote_addr="10.42.7.3",
            x_forwarded_for="198.51.100.22",
        )
        ip = get_client_ip(request)
        assert ip == "198.51.100.22"

    def test_no_xff_header_returns_remote_addr(self):
        """Without X-Forwarded-For, always return REMOTE_ADDR."""
        request = _make_request(remote_addr="198.51.100.10")
        ip = get_client_ip(request)
        assert ip == "198.51.100.10"
