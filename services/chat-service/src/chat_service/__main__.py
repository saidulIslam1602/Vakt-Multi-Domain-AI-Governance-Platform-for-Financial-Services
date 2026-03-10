"""Entry point: run the chat service with uvicorn."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "chat_service.presentation.api:_get_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
