from fastapi import APIRouter, UploadFile
from typing import List
from app.services.doc_extractor_service import process_document

router = APIRouter()

@router.post("/extract-from-document")
async def extract_from_document(file: UploadFile):
    """Extract multiple rules from a document (PDF/DOCX/TXT)"""
    rules = await process_document(file)
    return {"rules": rules}