from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.rule_test_service import test_rule_yaml_against_code

router = APIRouter()


class RuleTestIn(BaseModel):
    rule_yaml: str = Field(min_length=1)
    code: str = Field(default="")


@router.post("/rules/test")
def rules_test(payload: RuleTestIn):
    return test_rule_yaml_against_code(payload.rule_yaml, payload.code)
