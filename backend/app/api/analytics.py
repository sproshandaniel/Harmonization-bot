from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query, Request

from app.api.auth_context import get_request_user
from app.services.store_service import (
    compute_analytics_overview,
    compute_developer_analytics,
    list_analytics_developers,
)

router = APIRouter()


def _resolve_scope_user(user: str) -> str | None:
    # Architects can inspect broader analytics; others stay user-scoped.
    return None if "architect" in (user or "").lower() else user


def _resolve_period_bounds(
    period: str,
    start_date: str | None,
    end_date: str | None,
) -> tuple[str | None, str | None]:
    period_norm = (period or "week").lower()
    today = datetime.now(timezone.utc).date()
    if period_norm == "custom":
        return start_date, end_date
    if period_norm == "year":
        return (today - timedelta(days=365)).isoformat(), today.isoformat()
    if period_norm == "month":
        return (today - timedelta(days=30)).isoformat(), today.isoformat()
    return (today - timedelta(days=7)).isoformat(), today.isoformat()


@router.get("/analytics/overview")
def get_analytics_overview(
    request: Request,
    period: str = Query(default="week"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
):
    user = get_request_user(request)
    scoped_user = _resolve_scope_user(user)
    start_bound, end_bound = _resolve_period_bounds(period, start_date, end_date)
    return compute_analytics_overview(
        created_by=scoped_user,
        start_date=start_bound,
        end_date=end_bound,
    )


@router.get("/analytics/developers")
def get_developer_analytics(
    request: Request,
    period: str = Query(default="week"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    developer: str | None = Query(default=None),
):
    user = get_request_user(request)
    scoped_user = _resolve_scope_user(user)
    start_bound, end_bound = _resolve_period_bounds(period, start_date, end_date)
    return compute_developer_analytics(
        created_by=scoped_user,
        developer=developer,
        start_date=start_bound,
        end_date=end_bound,
    )


@router.get("/analytics/developer-options")
def get_analytics_developer_options(
    request: Request,
    period: str = Query(default="week"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
):
    user = get_request_user(request)
    scoped_user = _resolve_scope_user(user)
    start_bound, end_bound = _resolve_period_bounds(period, start_date, end_date)
    return {
        "developers": list_analytics_developers(
            created_by=scoped_user,
            start_date=start_bound,
            end_date=end_bound,
        )
    }
