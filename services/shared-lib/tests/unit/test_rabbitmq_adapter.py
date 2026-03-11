"""Unit tests for RabbitMQ adapter helper functions.

Tests the detection and URL-building logic without requiring a live
RabbitMQ broker (no aio-pika network calls are made).
"""

from __future__ import annotations

from allergo_shared.infrastructure.azure.rabbitmq import (
    _build_amqp_url,
    _is_amqp_url,
)

# ── _is_amqp_url ──────────────────────────────────────────────────────────────

class TestIsAmqpUrl:
    def test_rabbitmq_hostname(self):
        assert _is_amqp_url("rabbitmq:5672") is True

    def test_localhost(self):
        assert _is_amqp_url("localhost") is True

    def test_127_0_0_1(self):
        assert _is_amqp_url("127.0.0.1:5672") is True

    def test_amqp_scheme(self):
        assert _is_amqp_url("amqp://user:pass@rabbitmq:5672/") is True

    def test_amqps_scheme(self):
        assert _is_amqp_url("amqps://user:pass@rabbitmq:5672/") is True

    def test_azure_service_bus_not_detected(self):
        assert _is_amqp_url("mybus.servicebus.windows.net") is False

    def test_bare_host_port_detected_as_local(self):
        # any "host:port" that doesn't look like .servicebus.windows.net
        assert _is_amqp_url("broker:5672") is True

    def test_case_insensitive_rabbitmq(self):
        assert _is_amqp_url("RabbitMQ:5672") is True


# ── _build_amqp_url ───────────────────────────────────────────────────────────

class TestBuildAmqpUrl:
    def test_passthrough_full_amqp_url(self):
        url = "amqp://user:pass@rabbitmq:5672/"
        assert _build_amqp_url(url) == url

    def test_host_port_gets_default_creds(self):
        url = _build_amqp_url("rabbitmq:5672")
        assert url == "amqp://allergo:allergo@rabbitmq:5672/"

    def test_host_only_uses_default_port(self):
        url = _build_amqp_url("rabbitmq")
        assert url == "amqp://allergo:allergo@rabbitmq:5672/"

    def test_localhost_port(self):
        url = _build_amqp_url("localhost:5672")
        assert url == "amqp://allergo:allergo@localhost:5672/"

    def test_invalid_port_falls_back_to_5672(self):
        url = _build_amqp_url("rabbitmq:notaport")
        assert ":5672/" in url

    def test_amqps_passthrough(self):
        url = "amqps://user:pass@broker:5671/"
        assert _build_amqp_url(url) == url


# ── Integration: AzureServiceBus delegates to RabbitMQ locally ────────────────

class TestAzureServiceBusDelegation:
    """Verify the auto-delegation logic in AzureServiceBus.__init__."""

    def test_rabbitmq_endpoint_detected(self):
        # The helper is imported into service_bus from rabbitmq — test via rabbitmq module
        assert _is_amqp_url("rabbitmq:5672") is True

    def test_azure_service_bus_endpoint_not_detected(self):
        assert _is_amqp_url("mybus.servicebus.windows.net") is False

    def test_azure_service_bus_delegates_to_rabbitmq_adapter(self):
        """AzureServiceBus.__init__ should create a RabbitMQAdapter for local endpoints."""
        from unittest.mock import patch

        from allergo_shared.infrastructure.azure.rabbitmq import RabbitMQAdapter
        from allergo_shared.infrastructure.azure.service_bus import AzureServiceBus

        with patch.object(RabbitMQAdapter, "__init__", return_value=None):
            bus = AzureServiceBus("rabbitmq:5672")
            assert isinstance(bus._delegate, RabbitMQAdapter)
