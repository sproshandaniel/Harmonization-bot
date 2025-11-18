from fastapi import APIRouter, Form
from pydantic import BaseModel
from backend.app.services.extractor_service import extract_rule_pipeline

router = APIRouter()

class ExtractResult(BaseModel):
    yaml: str
    confidence: float
    rule_type: str
    rule_pack: str
    created_by: str
    duplicate_of: str | None = None
    similarity: float | None = None

@router.post("/extract-rule", response_model=ExtractResult)
async def extract_rule(
    text: str = Form(...),
    rule_type: str = Form("code"),
    rule_pack: str = Form("generic"),
    created_by: str = Form("anonymous"),
):
    """Extract a rule and capture metadata."""
    result = await extract_rule_pipeline(text, rule_type=rule_type)
    result["rule_type"] = rule_type
    result["rule_pack"] = rule_pack
    result["created_by"] = created_by
    return result