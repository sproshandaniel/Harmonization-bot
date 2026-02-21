from fastapi import APIRouter, Request
from fastapi import HTTPException, Query
from pydantic import BaseModel, Field

from app.api.auth_context import get_request_user
from app.services.store_service import (
    clear_all_fixed_dashboard_violations,
    clear_dashboard_violations_by_date_range,
    create_dashboard_violation,
    delete_dashboard_violation,
    get_dashboard_overview,
    get_managed_developers_for_architect,
    get_show_shared_rules_enabled,
    list_dashboard_violations,
)

router = APIRouter()


@router.get("/dashboard/overview")
def dashboard_overview(
    request: Request,
    include_all_developers: bool = Query(default=True),
):
    user = get_request_user(request)
    shared_visible = get_show_shared_rules_enabled(default=True)
    created_by_scope = None if shared_visible else user
    managed_developers = get_managed_developers_for_architect(user)
    if managed_developers:
        return get_dashboard_overview(created_by=created_by_scope, developers=managed_developers)
    return get_dashboard_overview(
        created_by=created_by_scope if include_all_developers else user,
    )


@router.get("/dashboard/violations")
def dashboard_violations(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    include_all_developers: bool = Query(default=True),
):
    user = get_request_user(request)
    shared_visible = get_show_shared_rules_enabled(default=True)
    managed_developers = get_managed_developers_for_architect(user) if shared_visible else []
    scoped_developer = None if managed_developers else (None if include_all_developers else user)
    return {
        "items": list_dashboard_violations(
            limit,
            developer=scoped_developer,
            developers=managed_developers or None,
        )
    }


class DashboardViolationIn(BaseModel):
    rule_pack: str = Field(min_length=1)
    object_name: str = Field(min_length=1)
    transport: str = Field(min_length=1)
    developer: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    status: str = "Not Fixed"


@router.post("/dashboard/violations")
def create_dashboard_violation_route(payload: DashboardViolationIn, request: Request):
    user = get_request_user(request)
    return create_dashboard_violation(
        payload.rule_pack,
        payload.object_name,
        payload.transport,
        user,
        payload.severity,
        payload.status,
    )


@router.delete("/dashboard/violations/clear-fixed")
def clear_fixed_dashboard_violations_route():
    deleted = clear_all_fixed_dashboard_violations()
    return {"deleted": deleted}


@router.delete("/dashboard/violations/{violation_id}")
def delete_dashboard_violation_route(violation_id: str):
    deleted = delete_dashboard_violation(violation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Violation not found")
    return {"deleted": True}


@router.delete("/dashboard/violations")
def clear_dashboard_violations_route(
    start_date: str = Query(..., description="Inclusive start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="Inclusive end date (YYYY-MM-DD)"),
):
    try:
        deleted = clear_dashboard_violations_by_date_range(start_date, end_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deleted": deleted, "start_date": start_date, "end_date": end_date}

