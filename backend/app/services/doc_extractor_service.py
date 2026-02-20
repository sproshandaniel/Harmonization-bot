import io
from fastapi import UploadFile
from app.services.extractor_service import extract_rules_multi_pipeline

# simple PDF text reader using PyMuPDF (install with: pip install PyMuPDF)
import fitz  

async def process_document(
    file: UploadFile,
    rule_type: str = "code",
    rule_types: list[str] | None = None,
    max_rules: int = 5,
    wizard_name: str | None = None,
    wizard_description: str | None = None,
    wizard_step_title: str | None = None,
    wizard_step_description: str | None = None,
    wizard_step_no: int | None = None,
    wizard_total_steps: int | None = None,
    template_use_ai: bool = False,
):
    filename = file.filename.lower()
    content = await file.read()

    # Extract text depending on file type
    if filename.endswith(".pdf"):
        text = extract_text_from_pdf(io.BytesIO(content))
    else:
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception:
            text = ""

    cleaned = "\n".join([line.strip() for line in text.splitlines() if line.strip()])
    rules = await extract_rules_multi_pipeline(
        cleaned[:12000],
        rule_types=rule_types or [rule_type],
        max_rules=max_rules,
        wizard_name=wizard_name,
        wizard_description=wizard_description,
        wizard_step_title=wizard_step_title,
        wizard_step_description=wizard_step_description,
        wizard_step_no=wizard_step_no,
        wizard_total_steps=wizard_total_steps,
        template_use_ai=template_use_ai,
    )
    for rule in rules:
        rule["source_snippet"] = f"Extracted from document: {file.filename}"
    return rules


def extract_text_from_pdf(file_bytes):
    text = ""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            text += page.get_text("text") + "\n"
    return text
