"""Queue port — abstraction over message broker (Azure Service Bus)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class MessageQueuePort(ABC):
    """Interface for message queue operations."""

    @abstractmethod
    async def publish(
        self,
        topic_or_queue: str,
        message: dict[str, Any],
        correlation_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Publish a message to a topic or queue."""

    @abstractmethod
    def subscribe(
        self,
        topic_or_queue: str,
        subscription: str | None = None,
    ) -> AsyncIterator[QueueMessage]:
        """Return an async iterator that yields messages from the queue."""


class QueueMessage(ABC):
    """Represents a received message from the queue."""

    def __init__(
        self,
        body: dict[str, Any],
        message_id: str,
        correlation_id: str | None = None,
        delivery_count: int = 1,
        raw: Any = None,
    ) -> None:
        self.body = body
        self.message_id = message_id
        self.correlation_id = correlation_id
        self.delivery_count = delivery_count
        self._raw = raw

    @abstractmethod
    async def complete(self) -> None:
        """Acknowledge the message as successfully processed."""

    @abstractmethod
    async def abandon(self) -> None:
        """Release the message back to the queue for retry."""

    @abstractmethod
    async def dead_letter(self, reason: str = "") -> None:
        """Move the message to the dead-letter queue."""
