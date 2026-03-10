"""Entry point: run the document service with uvicorn."""

import uvicorn
from document_service.presentation.config import get_settings

if __name__ == "__main__":
    cfg = get_settings()
    uvicorn.run(
        "document_service.presentation.api:_get_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        log_level=cfg.log_level.lower(),
        reload=cfg.environment == "development",
    )
