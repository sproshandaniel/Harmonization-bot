from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.auth_context import get_request_user
from app.services.bot_service import assist_with_rules

router = APIRouter()


class BotAssistIn(BaseModel):
    query: str = Field(min_length=1)
    code: str = ""
    object_name: str = "ADT_OBJECT"
    project_id: str | None = None
    pack_name: str | None = None
    developer: str | None = None
    transport: str = "ADT"
    top_k: int = Field(default=5, ge=1, le=10)
    log_violations: bool = True
    llm_fallback_confirmed: bool = False


@router.post("/bot/assist")
def bot_assist(request: Request, payload: BotAssistIn | None = None):
    if payload is None:
        payload = BotAssistIn(query="help")
    user = get_request_user(request)
    developer = payload.developer or user
    return assist_with_rules(
        query=payload.query,
        code=payload.code,
        object_name=payload.object_name,
        project_id=payload.project_id,
        pack_name=payload.pack_name,
        developer=developer,
        transport=payload.transport,
        created_by=user,
        top_k=payload.top_k,
        log_violations=payload.log_violations,
        llm_fallback_confirmed=payload.llm_fallback_confirmed,
    )


class BotValidateIn(BaseModel):
    code: str = ""
    object_name: str = "ADT_OBJECT"
    project_id: str | None = None
    pack_name: str | None = None
    developer: str | None = None
    transport: str = "ADT"
    top_k: int = Field(default=20, ge=1, le=50)
    log_violations: bool = True


@router.post("/bot/validate")
def bot_validate(request: Request, payload: BotValidateIn | None = None):
    if payload is None:
        payload = BotValidateIn()
    user = get_request_user(request)
    developer = payload.developer or user
    return assist_with_rules(
        query="validate current object against governance rules",
        code=payload.code,
        object_name=payload.object_name,
        project_id=payload.project_id,
        pack_name=payload.pack_name,
        developer=developer,
        transport=payload.transport,
        created_by=user,
        top_k=payload.top_k,
        log_violations=payload.log_violations,
    )
