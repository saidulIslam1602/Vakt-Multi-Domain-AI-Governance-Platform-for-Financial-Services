"""Entry point: run the search service with uvicorn."""

import uvicorn

from search_service.infrastructure.config import get_settings

if __name__ == "__main__":
    cfg = get_settings()
    uvicorn.run(
        "search_service.presentation.api:_get_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        log_level=cfg.log_level.lower(),
        reload=cfg.environment == "development",
    )
