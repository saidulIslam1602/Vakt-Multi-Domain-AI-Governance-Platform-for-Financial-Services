"""Immutable value objects used across all services."""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BaseModel, Field


class DocumentId(BaseModel):
    """Unique document identifier."""

    value: Annotated[str, Field(min_length=36, max_length=36)]

    model_config = {"frozen": True}

    @classmethod
    def generate(cls) -> "DocumentId":
        return cls(value=str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.value


class TenantId(BaseModel):
    """Tenant identifier for multi-tenant isolation."""

    value: Annotated[str, Field(min_length=1, max_length=128)]

    model_config = {"frozen": True}

    def __str__(self) -> str:
        return self.value
