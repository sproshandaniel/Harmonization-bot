from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.auth_context import get_request_user
from app.services.technical_doc_service import (
    enrich_technical_doc,
    generate_technical_doc,
    save_technical_doc,
)

router = APIRouter()


class GenerateDocIn(BaseModel):
    code: str = ""
    object_name: str = "ADT_OBJECT"
    developer: str | None = None
    project_id: str | None = None
    change_summary: str | None = None
    validation_summary: str | None = None


@router.post("/docs/generate")
def docs_generate(request: Request, payload: GenerateDocIn):
    user = get_request_user(request)
    developer = payload.developer or user
    result = generate_technical_doc(
        code=payload.code,
        object_name=payload.object_name,
        developer=developer,
        change_summary=payload.change_summary,
        validation_summary=payload.validation_summary,
    )
    result["project_id"] = payload.project_id
    return result


class EnrichDocIn(BaseModel):
    existing_document: str = Field(min_length=1)
    code: str = ""
    object_name: str = "ADT_OBJECT"
    developer: str | None = None
    project_id: str | None = None
    change_summary: str | None = None
    validation_summary: str | None = None


@router.post("/docs/enrich")
def docs_enrich(request: Request, payload: EnrichDocIn):
    user = get_request_user(request)
    developer = payload.developer or user
    result = enrich_technical_doc(
        existing_document=payload.existing_document,
        code=payload.code,
        object_name=payload.object_name,
        developer=developer,
        change_summary=payload.change_summary,
        validation_summary=payload.validation_summary,
    )
    result["project_id"] = payload.project_id
    return result


class SaveDocIn(BaseModel):
    title: str = "Technical Design"
    document: str = Field(min_length=1)
    object_name: str = "ADT_OBJECT"
    developer: str | None = None
    project_id: str | None = None


@router.post("/docs/save")
def docs_save(request: Request, payload: SaveDocIn):
    user = get_request_user(request)
    developer = payload.developer or user
    return save_technical_doc(
        title=payload.title,
        document=payload.document,
        object_name=payload.object_name,
        developer=developer,
        project_id=payload.project_id,
    )
