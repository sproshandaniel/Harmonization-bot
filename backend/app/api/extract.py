from fastapi import APIRouter, Form
from pydantic import BaseModel
from app.services.extractor_service import extract_rules_multi_pipeline

router = APIRouter()

class ExtractResult(BaseModel):
    yaml: str
    confidence: float
    duplicate_of: str | None = None
    similarity: float | None = None

class ExtractResponse(BaseModel):
    rules: list[ExtractResult]
    rule_type: str
    rule_types: list[str]
    rule_pack: str
    created_by: str


@router.post("/extract-rule", response_model=ExtractResponse)
async def extract_rule(
    text: str = Form(...),
    rule_type: str = Form("code"),
    rule_types: str | None = Form(default=None),
    max_rules: int = Form(5),
    wizard_name: str | None = Form(default=None),
    wizard_description: str | None = Form(default=None),
    wizard_step_title: str | None = Form(default=None),
    wizard_step_description: str | None = Form(default=None),
    wizard_step_snippet: str | None = Form(default=None),
    wizard_step_no: int | None = Form(default=None),
    wizard_total_steps: int | None = Form(default=None),
    template_use_ai: bool = Form(default=False),
    rule_pack: str = Form("generic"),
    created_by: str = Form("anonymous"),
    project_id: str | None = Form(None),
):
    """Extract a rule and capture metadata."""
    safe_max_rules = max(1, min(max_rules, 10))
    selected_types = [rule_type]
    if rule_types:
        parsed = [t.strip().lower() for t in rule_types.split(",") if t.strip()]
        if parsed:
            selected_types = parsed
    rules = await extract_rules_multi_pipeline(
        text,
        rule_types=selected_types,
        max_rules=safe_max_rules,
        wizard_name=wizard_name,
        wizard_description=wizard_description,
        wizard_step_title=wizard_step_title,
        wizard_step_description=wizard_step_description,
        wizard_step_snippet=wizard_step_snippet,
        wizard_step_no=wizard_step_no,
        wizard_total_steps=wizard_total_steps,
        template_use_ai=template_use_ai,
        created_by=created_by,
    )

    return {
        "rules": rules,
        "rule_type": "multi" if len(selected_types) > 1 else selected_types[0],
        "rule_types": selected_types,
        "rule_pack": rule_pack,
        "created_by": created_by,
    }
