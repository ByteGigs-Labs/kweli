import json
import logging

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from api.config import get_settings
from api.db.models import WebhookEvent
from api.db.session import get_db
from api.deps import get_paypal
from api.errors import error_body
from api.services.payments import handle_event
from paypal.client import PayPalClient
from paypal.errors import PayPalError
from paypal.webhooks import MissingSignature, verify

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])
logger = logging.getLogger("kweli.webhooks")


def _reply(code: int, kind: str, message: str) -> JSONResponse:
    return JSONResponse(error_body(kind, message), code)


@router.post("/paypal", include_in_schema=False)
async def paypal_webhook(
    request: Request,
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
):
    webhook_id = get_settings().paypal_webhook_id
    if not webhook_id:
        logger.error("PAYPAL_WEBHOOK_ID is not set; rejecting webhook")
        return _reply(503, "not_configured", "Webhook not configured")
    raw = await request.body()
    try:
        trusted = verify(paypal, request.headers, raw, webhook_id)
    except MissingSignature:
        return _reply(400, "bad_signature", "Missing PayPal signature headers")
    except (PayPalError, UnicodeDecodeError) as error:
        logger.warning("webhook verification unavailable: %s", type(error).__name__)
        return _reply(503, "verify_unavailable", "Couldn't verify the event; retry later")
    if not trusted:
        logger.warning("webhook rejected: signature check failed")
        return _reply(400, "bad_signature", "Signature check failed")

    event = json.loads(raw)
    event_id = str(event.get("id", ""))[:64]
    if not event_id:
        return _reply(400, "bad_event", "Event has no id")
    row = db.get(WebhookEvent, event_id)
    if row and row.status in ("processed", "ignored"):
        return {"status": "duplicate"}
    if not row:
        row = WebhookEvent(
            paypal_event_id=event_id,
            event_type=str(event.get("event_type", ""))[:80],
            resource_id=str(
                (event.get("resource") or {}).get("id")
                or (event.get("resource") or {}).get("dispute_id")
                or ""
            )[:64]
            or None,
        )
        db.add(row)
    row.attempts = (row.attempts or 0) + 1
    row.status = "received"
    db.commit()

    try:
        outcome = handle_event(db, paypal, event)
    except Exception as error:  # noqa: BLE001 - any failure means PayPal should retry
        db.rollback()
        row = db.get(WebhookEvent, event_id)
        row.status = "failed"
        row.note = type(error).__name__[:300]
        db.commit()
        logger.error("webhook %s failed: %s", event_id, type(error).__name__)
        return JSONResponse(
            error_body("processing_failed", "Couldn't process the event; retry later"),
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    row.status = outcome.status
    row.note = outcome.note[:300]
    db.commit()
    return {"status": outcome.status}
