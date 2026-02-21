from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.store_service import (
    backfill_template_metadata,
    create_rule_pack_option,
    delete_rule_pack_option,
    get_llm_usage_daily_cost,
    get_rule_pack_options,
    get_app_settings,
    get_ui_config,
    list_rule_pack_option_rows,
    update_app_settings,
    update_ui_config,
)

router = APIRouter()


@router.get("/settings")
def app_settings():
    return get_app_settings()


@router.get("/settings/llm-usage/daily-cost")
def llm_usage_daily_cost(days: int = Query(default=30, ge=1, le=365)):
    return get_llm_usage_daily_cost(days=days)


@router.put("/settings")
def update_app_settings_route(payload: dict[str, Any]):
    if not isinstance(payload, dict) or not payload:
        raise HTTPException(status_code=400, detail="Settings payload is required")
    return update_app_settings(payload)


@router.get("/ui-config")
def ui_config():
    return get_ui_config()


class UIConfigUpdateIn(BaseModel):
    app_footer: str | None = None
    platform_title: str | None = None
    default_user: str | None = None


@router.put("/ui-config")
def update_ui_config_route(payload: UIConfigUpdateIn):
    updates = {k: v for k, v in payload.model_dump().items() if isinstance(v, str)}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid config fields provided")
    return update_ui_config(updates)


@router.get("/rule-pack-options")
def rule_pack_options(rule_type: str = Query(...)):
    return {"rule_type": rule_type, "options": get_rule_pack_options(rule_type)}


@router.get("/rule-pack-options/all")
def rule_pack_options_all(rule_type: str | None = Query(default=None)):
    return {"items": list_rule_pack_option_rows(rule_type)}


class RulePackOptionIn(BaseModel):
    rule_type: str = Field(min_length=1)
    pack_name: str = Field(min_length=1)


class BackfillTemplateMetadataIn(BaseModel):
    limit: int = Field(default=5000, ge=1, le=20000)


@router.post("/rule-pack-options")
def create_rule_pack_option_route(payload: RulePackOptionIn):
    return create_rule_pack_option(payload.rule_type, payload.pack_name)


@router.delete("/rule-pack-options/{option_id}")
def delete_rule_pack_option_route(option_id: str):
    deleted = delete_rule_pack_option(option_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule pack option not found")
    return {"deleted": True}


@router.post("/maintenance/backfill-template-metadata")
def backfill_template_metadata_route(payload: BackfillTemplateMetadataIn):
    return backfill_template_metadata(limit=payload.limit)
