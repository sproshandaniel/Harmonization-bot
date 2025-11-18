import io
from fastapi import UploadFile
from app.services.extractor_service import extract_rule_pipeline

# simple PDF text reader using PyMuPDF (install with: pip install PyMuPDF)
import fitz  

async def process_document(file: UploadFile):
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

    # For now, treat each paragraph as one rule candidate
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    results = []
    for para in paragraphs[:5]:  # limit to first 5 for demo
        rule = await extract_rule_pipeline(para)
        rule["source_snippet"] = para
        results.append(rule)
    return results


def extract_text_from_pdf(file_bytes):
    text = ""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            text += page.get_text("text") + "\n"
    return text
