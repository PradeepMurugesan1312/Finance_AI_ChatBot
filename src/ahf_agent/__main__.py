"""Entrypoint: `python -m ahf_agent`."""

import uvicorn

from ahf_agent.config import get_settings
from ahf_agent.server import create_app


def main() -> None:
    settings = get_settings()
    app = create_app(settings)
    # log_config=None: keep structlog's JSON output as the single log format
    # instead of letting uvicorn install its own.
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_config=None)


if __name__ == "__main__":
    main()
