from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.errors import install_error_handlers
from api.limits import BodySizeLimit
from api.logging_config import RequestLog, setup_logging
from api.routes import (
    agent,
    agreements,
    audit,
    auth,
    clients,
    disputes,
    documents,
    invoices,
    ledger,
    packs,
    portal,
    readiness,
    webhooks,
)


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="Kweli API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Total-Count", "X-Request-ID"],
    )
    app.add_middleware(BodySizeLimit, upload_prefixes=("/v1/documents", "/v1/disputes"))
    app.add_middleware(RequestLog)
    install_error_handlers(app)
    for module in (
        auth,
        clients,
        agreements,
        invoices,
        portal,
        webhooks,
        audit,
        documents,
        ledger,
        readiness,
        packs,
        disputes,
        agent,
    ):
        app.include_router(module.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
