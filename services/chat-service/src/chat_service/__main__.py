"""Entry point: run the chat service with uvicorn."""

import uvicorn

from chat_service.presentation.api import Settings
from allergo_shared.infrastructure.logging import configure_logging

if __name__ == "__main__":
    cfg = Settings()  # type: ignore[call-arg]
    configure_logging(cfg.service_name, cfg.log_level)
    uvicorn.run(
        "chat_service.presentation.api:_get_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        log_level=cfg.log_level.lower(),
        reload=cfg.environment == "development",
    )
