"""AI care — process entry point.

Runs FastAPI from app/server/webhook.py. FastAPI owns the full lifecycle:
  application.initialize() → application.start() → scheduler.start() → set_webhook()
"""

import uvicorn

from app.config import settings


def main() -> None:
    uvicorn.run(
        "app.server.webhook:app",
        host="0.0.0.0",
        port=8000,
        log_level=settings.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
