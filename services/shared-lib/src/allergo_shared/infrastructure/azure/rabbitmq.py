"""RabbitMQ / AMQP queue adapter — implements MessageQueuePort.

Used in local development (docker-compose) where Azure Service Bus is
replaced by a RabbitMQ container.  The adapter uses ``aio-pika`` for
async AMQP communication and mirrors the behaviour of the Azure Service
Bus adapter as closely as possible:

* ``publish``  → declares a fanout exchange and publishes the JSON body.
* ``subscribe`` → declares an exclusive queue bound to the exchange and
  yields messages one at a time.

Dead-lettering is emulated by publishing to a ``<topic>.dead-letter``
exchange.  ``abandon`` re-queues the message via nack with requeue=True
up to *max_delivery_count* retries, then dead-letters it.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from allergo_shared.domain.exceptions import QueueError
from allergo_shared.domain.interfaces.queue import MessageQueuePort, QueueMessage
from allergo_shared.infrastructure.logging import get_logger

logger = get_logger(__name__)

_MAX_DELIVERY_COUNT = 3


def _is_amqp_url(fqdn: str) -> bool:
    """Return True when the FQDN looks like a RabbitMQ host (not an Azure namespace)."""
    lower = fqdn.lower()
    return (
        lower.startswith("amqp://")
        or lower.startswith("amqps://")
        or "rabbitmq" in lower
        or "localhost" in lower
        or "127.0.0.1" in lower
        or ":" in lower  # host:port  e.g. rabbitmq:5672
    )


def _build_amqp_url(fqdn: str) -> str:
    """Convert a bare ``host:port`` or hostname into a full amqp:// URL."""
    if fqdn.startswith("amqp"):
        return fqdn
    host = fqdn
    port = 5672
    if ":" in fqdn:
        parts = fqdn.split(":", 1)
        host = parts[0]
        try:
            port = int(parts[1])
        except ValueError:
            pass
    return f"amqp://allergo:allergo@{host}:{port}/"


class RabbitMQAdapter(MessageQueuePort):
    """aio-pika–backed message queue for local development with RabbitMQ."""

    def __init__(self, amqp_url: str) -> None:
        self._amqp_url = amqp_url
        self._connection: Any = None
        self._channel: Any = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _get_channel(self) -> Any:
        """Lazily create an aio-pika connection + channel."""
        try:
            import aio_pika
        except ImportError as exc:
            raise QueueError(
                "aio-pika is required for RabbitMQ support. "
                "Add 'aio-pika>=9.4' to the service's dependencies."
            ) from exc

        if self._connection is None or self._connection.is_closed:
            self._connection = await aio_pika.connect_robust(self._amqp_url)
        if self._channel is None or self._channel.is_closed:
            self._channel = await self._connection.channel()
        return self._channel

    async def _declare_exchange(self, channel: Any, name: str) -> Any:
        import aio_pika
        return await channel.declare_exchange(
            name,
            aio_pika.ExchangeType.FANOUT,
            durable=True,
        )

    # ── MessageQueuePort interface ────────────────────────────────────────────

    async def publish(
        self,
        topic_or_queue: str,
        message: dict[str, Any],
        correlation_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        try:
            import aio_pika
            channel = await self._get_channel()
            exchange = await self._declare_exchange(channel, topic_or_queue)
            body = json.dumps(message, default=str).encode()
            amqp_message = aio_pika.Message(
                body=body,
                content_type="application/json",
                message_id=correlation_id or str(uuid.uuid4()),
                correlation_id=correlation_id,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )
            await exchange.publish(amqp_message, routing_key="")
            logger.debug(
                "rabbitmq_published",
                topic=topic_or_queue,
                correlation_id=correlation_id,
            )
        except Exception as exc:
            raise QueueError(f"Failed to publish to '{topic_or_queue}': {exc}") from exc

    def subscribe(
        self,
        topic_or_queue: str,
        subscription: str | None = None,
    ) -> AsyncIterator[QueueMessage]:
        return self._message_generator(topic_or_queue, subscription)

    async def _message_generator(
        self,
        topic_or_queue: str,
        subscription: str | None,
    ) -> AsyncIterator[QueueMessage]:
        try:
            channel = await self._get_channel()
            await channel.set_qos(prefetch_count=1)
            exchange = await self._declare_exchange(channel, topic_or_queue)

            # Each worker gets a uniquely named durable queue so messages
            # survive restarts, but multiple workers of the same subscription
            # share the same queue for competing-consumers semantics.
            queue_name = f"{topic_or_queue}.{subscription or 'default'}"
            queue = await channel.declare_queue(queue_name, durable=True)
            await queue.bind(exchange)

            async with queue.iterator() as q_iter:
                async for msg in q_iter:
                    body = json.loads(msg.body.decode())
                    delivery_count = (msg.headers or {}).get("x-delivery-count", 1)
                    yield _RabbitMQMessage(
                        body=body,
                        message_id=str(msg.message_id or uuid.uuid4()),
                        correlation_id=str(msg.correlation_id) if msg.correlation_id else None,
                        delivery_count=int(delivery_count),
                        raw=msg,
                        topic=topic_or_queue,
                        channel=channel,
                    )
        except Exception as exc:
            raise QueueError(f"Failed to subscribe to '{topic_or_queue}': {exc}") from exc

    async def close(self) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
        self._connection = None
        self._channel = None


class _RabbitMQMessage(QueueMessage):
    """Concrete RabbitMQ message with ack / nack / dead-letter support."""

    def __init__(
        self,
        *,
        raw: Any,
        topic: str,
        channel: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._raw = raw
        self._topic = topic
        self._channel = channel

    async def complete(self) -> None:
        await self._raw.ack()

    async def abandon(self) -> None:
        if self.delivery_count >= _MAX_DELIVERY_COUNT:
            await self.dead_letter(reason="max_delivery_count_exceeded")
        else:
            await self._raw.nack(requeue=True)

    async def dead_letter(self, reason: str = "") -> None:
        # Publish to a dead-letter exchange then ack original
        try:
            import aio_pika
            dl_exchange = await self._channel.declare_exchange(
                f"{self._topic}.dead-letter",
                aio_pika.ExchangeType.FANOUT,
                durable=True,
            )
            headers = dict(self._raw.headers or {})
            headers["x-dead-letter-reason"] = reason
            dl_msg = aio_pika.Message(
                body=self._raw.body,
                content_type="application/json",
                headers=headers,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )
            await dl_exchange.publish(dl_msg, routing_key="")
        except Exception:
            logger.exception("dead_letter_publish_failed", topic=self._topic)
        finally:
            await self._raw.ack()
