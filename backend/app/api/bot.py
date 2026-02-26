from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.auth_context import get_request_user
from app.services.bot_service import (
    advance_wizard_conversation,
    assist_with_rules,
    explain_abap_code,
    get_wizard_conversation_status,
    start_wizard_conversation,
)

router = APIRouter()


class BotAssistIn(BaseModel):
    query: str = Field(min_length=1)
    code: str = ""
    object_name: str = "ADT_OBJECT"
    project_id: str | None = None
    pack_name: str | None = None
    developer: str | None = None
    transport: str = ""
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
    transport: str = ""
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


class BotWizardStartIn(BaseModel):
    query: str = Field(default="start wizard")
    wizard_id: str | None = None
    project_id: str | None = None
    developer: str | None = None
    force_restart: bool = False


@router.post("/bot/wizard/start")
def bot_wizard_start(request: Request, payload: BotWizardStartIn | None = None):
    if payload is None:
        payload = BotWizardStartIn()
    user = get_request_user(request)
    developer = payload.developer or user
    return start_wizard_conversation(
        query=payload.query,
        developer=developer,
        created_by=user,
        project_id=payload.project_id,
        wizard_id=payload.wizard_id,
        force_restart=payload.force_restart,
    )


class BotWizardNextIn(BaseModel):
    session_id: str = Field(min_length=1)
    developer: str | None = None
    message: str = "done"


@router.post("/bot/wizard/next")
def bot_wizard_next(request: Request, payload: BotWizardNextIn):
    user = get_request_user(request)
    developer = payload.developer or user
    return advance_wizard_conversation(
        session_id=payload.session_id,
        developer=developer,
        user_message=payload.message,
    )


class BotWizardStatusIn(BaseModel):
    session_id: str | None = None
    project_id: str | None = None
    developer: str | None = None


@router.post("/bot/wizard/status")
def bot_wizard_status(request: Request, payload: BotWizardStatusIn | None = None):
    if payload is None:
        payload = BotWizardStatusIn()
    user = get_request_user(request)
    developer = payload.developer or user
    return get_wizard_conversation_status(
        developer=developer,
        project_id=payload.project_id,
        session_id=payload.session_id,
    )


class BotExplainIn(BaseModel):
    code: str = ""
    object_name: str = "ADT_OBJECT"
    project_id: str | None = None
    developer: str | None = None


@router.post("/bot/explain")
def bot_explain(request: Request, payload: BotExplainIn | None = None):
    if payload is None:
        payload = BotExplainIn()
    user = get_request_user(request)
    developer = payload.developer or user
    return explain_abap_code(
        code=payload.code,
        object_name=payload.object_name,
        developer=developer,
        created_by=user,
        project_id=payload.project_id,
    )
