from fastapi import APIRouter

router = APIRouter()

@router.get("/rules/summary")
def get_rule_summary():
    # Replace these with real DB queries
    return {
        "code": 58,
        "design": 23,
        "naming": 35,
        "performance": 19,
        "template": 12,
        "total": 147,
    }
