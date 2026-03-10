"""Azure Service Bus adapter — implements MessageQueuePort."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from azure.identity.aio import DefaultAzureCredential
from azure.servicebus.aio import ServiceBusClient, ServiceBusReceiver
from azure.servicebus import ServiceBusMessage

from allergo_shared.domain.exceptions import QueueError
from allergo_shared.domain.interfaces.queue import MessageQueuePort, QueueMessage


class AzureServiceBus(MessageQueuePort):
    """Production Azure Service Bus implementation."""

    def __init__(self, namespace_fqdn: str) -> None:
        self._namespace_fqdn = namespace_fqdn
        self._credential = DefaultAzureCredential()
        self._client = ServiceBusClient(
            fully_qualified_namespace=namespace_fqdn,
            credential=self._credential,
        )

    async def publish(
        self,
        topic_or_queue: str,
        message: dict[str, Any],
        correlation_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        try:
            async with self._client.get_topic_sender(topic_or_queue) as sender:
                sb_message = ServiceBusMessage(
                    body=json.dumps(message),
                    content_type="application/json",
                    correlation_id=correlation_id,
                    session_id=session_id,
                )
                await sender.send_messages(sb_message)
        except Exception as exc:
            raise QueueError(f"Failed to publish message to '{topic_or_queue}': {exc}") from exc

    def subscribe(
        self,
        topic_or_queue: str,
        subscription: str | None = None,
    ) -> AsyncIterator[QueueMessage]:
        """Return an async generator that yields QueueMessage objects."""
        return self._message_generator(topic_or_queue, subscription)

    async def _message_generator(
        self,
        topic_or_queue: str,
        subscription: str | None,
    ) -> AsyncIterator[QueueMessage]:
        try:
            if subscription:
                receiver: ServiceBusReceiver = self._client.get_subscription_receiver(
                    topic_name=topic_or_queue,
                    subscription_name=subscription,
                )
            else:
                receiver = self._client.get_queue_receiver(queue_name=topic_or_queue)

            async with receiver:
                async for msg in receiver:
                    body = json.loads(str(msg))
                    yield _AzureQueueMessage(
                        body=body,
                        message_id=str(msg.message_id),
                        correlation_id=str(msg.correlation_id) if msg.correlation_id else None,
                        delivery_count=msg.delivery_count or 1,
                        receiver=receiver,
                        raw=msg,
                    )
        except Exception as exc:
            raise QueueError(f"Failed to subscribe to '{topic_or_queue}': {exc}") from exc

    async def close(self) -> None:
        await self._client.close()
        await self._credential.close()


class _AzureQueueMessage(QueueMessage):
    """Concrete Azure Service Bus message with ack/nack support."""

    def __init__(self, *, receiver: ServiceBusReceiver, raw: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._receiver = receiver
        self._raw = raw

    async def complete(self) -> None:
        await self._receiver.complete_message(self._raw)

    async def abandon(self) -> None:
        await self._receiver.abandon_message(self._raw)

    async def dead_letter(self, reason: str = "") -> None:
        await self._receiver.dead_letter_message(self._raw, reason=reason)
