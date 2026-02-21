from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth_context import get_request_user
from app.services.store_service import (
    add_rule_for_project,
    create_project,
    get_show_shared_rules_enabled,
    get_rules_for_project,
    list_projects,
    update_project,
)

router = APIRouter()


class ProjectMemberIn(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    role: str = Field(default="developer")


class ProjectCreateIn(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    members: list[ProjectMemberIn] = Field(default_factory=list)


class ProjectRuleSaveIn(BaseModel):
    yaml: str = Field(min_length=1)
    confidence: float = 0.7
    category: str | None = None
    _id: str | None = None
    _severity: str | None = None
    created_by: str = "architect"
    rule_pack: str = "manual"


@router.get("/projects")
def get_projects():
    return list_projects()


@router.post("/projects")
def post_project(payload: ProjectCreateIn):
    if not payload.members:
        raise HTTPException(status_code=400, detail="At least one member is required")
    return create_project(
        name=payload.name,
        description=payload.description,
        members=[member.model_dump() for member in payload.members],
    )


@router.put("/projects/{project_id}")
def put_project(project_id: str, payload: ProjectCreateIn):
    if not payload.members:
        raise HTTPException(status_code=400, detail="At least one member is required")
    updated = update_project(
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        members=[member.model_dump() for member in payload.members],
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated


@router.get("/projects/{project_id}/rules")
def get_project_rules(project_id: str, request: Request):
    user = get_request_user(request)
    shared_visible = get_show_shared_rules_enabled(default=True)
    # Project rules are shared artifacts across project members.
    return {"rules": get_rules_for_project(project_id, created_by=None if shared_visible else user)}


@router.post("/projects/{project_id}/rules")
def save_project_rule(project_id: str, payload: ProjectRuleSaveIn, request: Request):
    user = get_request_user(request)
    add_rule_for_project(
        project_id,
        payload.model_dump(),
        status="saved",
        source_type="manual",
        created_by=user,
    )
    return {"saved": True}
