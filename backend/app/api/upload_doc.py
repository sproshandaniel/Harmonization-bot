from fastapi import APIRouter, UploadFile, File, Form
from app.services.doc_extractor_service import process_document

router = APIRouter()

@router.post("/extract-from-document")
async def extract_from_document(
    file: UploadFile = File(...),
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
    project_id: str | None = Form(None),
    created_by: str = Form("anonymous"),
):
    """Extract multiple rules from a document (PDF/DOCX/TXT)"""
    safe_max_rules = max(1, min(max_rules, 10))
    selected_types = [rule_type]
    if rule_types:
        parsed = [t.strip().lower() for t in rule_types.split(",") if t.strip()]
        if parsed:
            selected_types = parsed
    rules = await process_document(
        file,
        rule_type=rule_type,
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

    return {"rules": rules, "rule_types": selected_types}
