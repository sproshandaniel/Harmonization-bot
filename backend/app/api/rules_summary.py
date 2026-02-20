from fastapi import APIRouter, Request
from app.api.auth_context import get_request_user
from app.services.store_service import get_rule_summary as get_rule_summary_data

router = APIRouter()

@router.get("/rules/summary")
def get_rule_summary(request: Request):
    user = get_request_user(request)
    return get_rule_summary_data(created_by=user)
