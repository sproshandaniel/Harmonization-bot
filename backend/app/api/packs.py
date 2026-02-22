from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.auth_context import get_request_user
from app.services.store_service import (
    delete_rule_by_row_id,
    delete_rule_pack,
    get_rules_for_pack,
    get_show_shared_rules_enabled,
    list_rule_packs,
    save_rule_pack,
    update_rule_yaml_by_row_id,
)

router = APIRouter()


class RulePackIn(BaseModel):
    name: str = Field(min_length=1)
    status: str = "draft"
    project_id: str | None = None
    rules: list[dict] = Field(default_factory=list)


class RuleYamlUpdateIn(BaseModel):
    yaml: str = Field(min_length=1)


@router.get("/packs")
def get_packs(request: Request):
    user = get_request_user(request)
    shared_visible = get_show_shared_rules_enabled(default=True)
    return {"packs": list_rule_packs(created_by=None if shared_visible else user)}


@router.get("/packs/{pack_name}/rules")
def get_pack_rules(
    pack_name: str,
    request: Request,
    project_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
):
    user = get_request_user(request)
    shared_visible = get_show_shared_rules_enabled(default=True)
    return {
        "pack_name": pack_name,
        "rules": get_rules_for_pack(
            pack_name,
            project_id=project_id,
            created_by=None if shared_visible else user,
            q=q,
        ),
    }


@router.delete("/packs/{pack_name}")
def delete_pack(pack_name: str, request: Request):
    user = get_request_user(request)
    shared_visible = get_show_shared_rules_enabled(default=True)
    deleted_rules = delete_rule_pack(pack_name, created_by=None if shared_visible else user)
    return {"deleted": True, "deleted_rules": deleted_rules}


@router.delete("/packs/{pack_name}/rules/{rule_row_id}")
def delete_pack_rule(pack_name: str, rule_row_id: int, request: Request):
    user = get_request_user(request)
    deleted = delete_rule_by_row_id(pack_name, rule_row_id, created_by=user)
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found in pack")
    return {"deleted": True}


@router.put("/packs/{pack_name}/rules/{rule_row_id}")
def update_pack_rule(pack_name: str, rule_row_id: int, payload: RuleYamlUpdateIn, request: Request):
    user = get_request_user(request)
    try:
        updated = update_rule_yaml_by_row_id(
            pack_name=pack_name,
            row_id=rule_row_id,
            yaml_text=payload.yaml,
            created_by=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Rule not found in pack")
    return {"updated": True, "rule": updated}


@router.post("/packs")
def post_pack(payload: RulePackIn, request: Request):
    user = get_request_user(request)
    return save_rule_pack(
        name=payload.name,
        status=payload.status,
        project_id=payload.project_id,
        rules=payload.rules,
        created_by=user,
    )
