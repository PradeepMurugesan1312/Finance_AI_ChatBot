"""Builds the ASGI app: A2A protocol routes (agent card + JSON-RPC task
lifecycle) plus a Cloud Foundry health check endpoint.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.utils.constants import DEFAULT_RPC_URL
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ahf_agent.agent_card import build_agent_card
from ahf_agent.config import Settings, get_settings
from ahf_agent.executor import FinanceAssistantExecutor
from ahf_agent.logging_config import configure_logging, get_logger

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    agent_card = build_agent_card(settings)

    # In-memory task store is fine for this stub (single-turn, no history to
    # persist); step 5's async webhook pattern will need a durable store so
    # tasks survive an instance restart mid-lookup.
    request_handler = DefaultRequestHandler(
        agent_executor=FinanceAssistantExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "service_starting",
            service=settings.service_name,
            environment=settings.environment,
            version=settings.service_version,
        )
        yield
        await request_handler.aclose()
        logger.info("service_stopped", service=settings.service_name)

    app = FastAPI(
        title=agent_card.name,
        description=agent_card.description,
        version=settings.service_version,
        lifespan=lifespan,
    )

    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(agent_card),
        jsonrpc_routes=create_jsonrpc_routes(
            request_handler,
            rpc_url=DEFAULT_RPC_URL,
            # Joule's A2A client currently speaks the v0.3 JSON-RPC method
            # names (e.g. `message/send`), not the v1.0 names (`SendMessage`)
            # this SDK defaults to. Accept both on the same endpoint so this
            # agent works with Joule today and with v1.0-native clients.
            enable_v0_3_compat=True,
        ),
    )

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> JSONResponse:
        """Liveness/readiness probe - wired up as the CF health-check-http-endpoint in step 7."""
        return JSONResponse({"status": "ok", "service": settings.service_name})

    return app


app = create_app()
