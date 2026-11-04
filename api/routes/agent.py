from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from agent import actions
from agent.runtime import run_turn
from agent.tools import Toolbox
from api.config import get_settings
from api.db.models import AgentAction
from api.db.session import get_db
from api.deps import get_llm, get_paypal
from api.ratelimit import limit_by_key
from api.security import Principal, current_principal
from api.services.invoicing import ServiceError
from paypal.client import PayPalClient

router = APIRouter(prefix="/v1/agent", tags=["agent"])


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[Message] = Field(min_length=1, max_length=20)

    @field_validator("messages")
    @classmethod
    def ends_with_user(cls, messages: list[Message]) -> list[Message]:
        if messages[-1].role != "user":
            raise ValueError("The last message must be from the user")
        return messages


class Detail(BaseModel):
    label: str
    value: str


class ActionOut(BaseModel):
    id: UUID
    kind: str
    title: str
    details: list[Detail]
    status: str
    expires_at: datetime
    token: str | None = None
    result: dict | None = None

    @classmethod
    def build(cls, action: AgentAction, token: str | None = None) -> "ActionOut":
        preview = action.arguments.get("preview", {})
        return cls(
            id=action.id,
            kind=action.tool,
            title=preview.get("title", action.tool),
            details=[
                Detail(label=label, value=value) for label, value in preview.get("details", [])
            ],
            status=action.status,
            expires_at=actions.expires_at(action),
            token=token,
            result=action.result,
        )


class StepOut(BaseModel):
    tool: str
    label: str
    ok: bool


class ReplyOut(BaseModel):
    reply: str
    steps: list[StepOut]
    actions: list[ActionOut]


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=10, max_length=100)


def _http(error: ServiceError) -> HTTPException:
    return HTTPException(error.status, error.message)


@router.post("/messages")
def send_message(
    body: Conversation,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
    llm=Depends(get_llm),
) -> ReplyOut:
    if llm is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The assistant isn't set up here yet. Everything it does is also on the other pages.",
        )
    settings = get_settings()
    limit_by_key(db, "agent", str(principal.user_id), settings.agent_messages_per_minute)
    toolbox = Toolbox(db, principal.user_id, paypal)
    history = [message.model_dump() for message in body.messages]
    try:
        reply = run_turn(llm, toolbox, principal.name, history, settings.agent_max_steps)
    except Exception as error:  # noqa: BLE001 - provider failure; proposals already stored
        db.rollback()
        if toolbox.proposals:
            reply = None
        else:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                "The assistant couldn't answer just now. Try again in a moment.",
            ) from error
    return ReplyOut(
        reply=reply.text if reply else "I've prepared that for you to approve.",
        steps=[StepOut(tool=s.tool, label=s.label, ok=s.ok) for s in toolbox.steps],
        actions=[ActionOut.build(p.action, p.token) for p in toolbox.proposals],
    )


@router.get("/actions")
def pending_actions(
    principal: Principal = Depends(current_principal), db: Session = Depends(get_db)
) -> list[ActionOut]:
    rows = db.scalars(
        select(AgentAction)
        .where(AgentAction.user_id == principal.user_id, AgentAction.status == "proposed")
        .order_by(AgentAction.created_at.desc())
        .limit(20)
    )
    return [ActionOut.build(row) for row in rows]


@router.post("/actions/{action_id}/approve")
def approve_action(
    action_id: UUID,
    body: Approval,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
    paypal: PayPalClient = Depends(get_paypal),
) -> ActionOut:
    try:
        action = actions.approve(db, principal.user_id, action_id, body.token, paypal)
    except ServiceError as error:
        raise _http(error) from None
    return ActionOut.build(action)


@router.post("/actions/{action_id}/reject")
def reject_action(
    action_id: UUID,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> ActionOut:
    try:
        action = actions.reject(db, principal.user_id, action_id)
    except ServiceError as error:
        raise _http(error) from None
    return ActionOut.build(action)
