from fastapi import APIRouter, Form
from pydantic import BaseModel
from app.services.extractor_service import extract_rule_pipeline

router = APIRouter()

class ExtractResult(BaseModel):
    yaml: str
    confidence: float
    duplicate_of: str | None = None
    similarity: float | None = None

@router.post("/extract-rule", response_model=ExtractResult)
async def extract_rule(text: str = Form(...)):
    """Extract a single rule from pasted text/code"""
    result = await extract_rule_pipeline(text)
    return result