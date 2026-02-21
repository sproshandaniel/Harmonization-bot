from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth_context import get_request_user
from app.services.store_service import delete_wizard, save_wizard

router = APIRouter()


class WizardStepIn(BaseModel):
    yaml: str = Field(min_length=1)
    confidence: float = 0.7
    category: str | None = None
    _id: str | None = None
    _severity: str | None = None


class WizardSaveIn(BaseModel):
    project_id: str = Field(min_length=1)
    wizard_name: str = Field(min_length=1)
    wizard_description: str = Field(min_length=1)
    total_steps: int = Field(ge=1)
    steps: list[WizardStepIn] = Field(min_length=1)
    rule_pack: str | None = None


@router.post("/wizards")
def save_wizard_route(payload: WizardSaveIn, request: Request):
    user = get_request_user(request)
    try:
        result = save_wizard(
            project_id=payload.project_id,
            wizard_name=payload.wizard_name,
            wizard_description=payload.wizard_description,
            total_steps=payload.total_steps,
            steps=[step.model_dump() for step in payload.steps],
            created_by=user,
            rule_pack=payload.rule_pack,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.delete("/wizards/{wizard_id}")
def delete_wizard_route(wizard_id: str, request: Request):
    user = get_request_user(request)
    deleted = delete_wizard(wizard_id, created_by=user)
    if not deleted:
        raise HTTPException(status_code=404, detail="Wizard not found")
    return {"deleted": True}
