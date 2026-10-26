"""REST endpoints implementing the DDICDI_generator_gen2 API specification for CDIF converters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from pydantic import ValidationError

from .. import __version__
from ..config import settings
from ..engine import (
    convert_cdif_to_target,
    convert_source_to_cdif,
    detect_file_format,
    extract_variables_and_preview,
)
from .schemas import (
    FileInfo,
    GenerateRequest,
    HealthOut,
    NewVariableIn,
    OutputRequest,
    RolesIn,
    VariableOut,
    VariablePatchIn,
)
from .store import UploadNotFound, UploadStore

router = APIRouter(prefix="/api")

SUPPORTED_EXTENSIONS = [".json", ".jsonld", ".xml", ".txt", ".tsv", ".csv"]


def get_store(request: Request) -> UploadStore:
    return request.app.state.store


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")


def _download(output_str: str, filename: str, target_format: str) -> Response:
    base = Path(filename).stem
    ext = "jsonld" if target_format in ("cdif", "croissant", "rocrate") else "json"
    download_name = f"{base}_{target_format.upper()}.{ext}"
    return Response(
        content=output_str.encode("utf-8"),
        media_type="application/ld+json",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


def _load_meta(store: UploadStore, file_id: str) -> dict:
    try:
        return store.load_meta(file_id)
    except UploadNotFound:
        raise HTTPException(status_code=404, detail=f"Unknown file_id {file_id}")


def _execute_conversion(store: UploadStore, file_id: str, target_format: str) -> dict:
    meta = _load_meta(store, file_id)
    src_file = store.get_source_file(file_id)
    content_str = src_file.read_text(encoding="utf-8", errors="replace")
    src_format = meta.get("file_format", "unknown")

    # 1. Convert source format -> CDIF
    cdif_doc = convert_source_to_cdif(src_file, src_format, content_str)

    # 2. Convert CDIF -> Target format
    target_format = target_format or meta.get("target_format", "cdif")
    output_doc = convert_cdif_to_target(cdif_doc, target_format)
    return output_doc


# -- info -----------------------------------------------------------------------------


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(
        status="healthy",
        version=__version__,
        service="CDIF Multi-Format Converter API"
    )


@router.get("/info")
def info() -> dict:
    return {
        "service": "CDIF Multi-Format Converter API",
        "version": __version__,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "supported_source_formats": [
            "croissant", "soso", "dcat", "ddi", "rocrate", "umm", "fair2", "cdif"
        ],
        "supported_target_formats": [
            "cdif", "croissant", "soso", "rocrate"
        ],
        "output_format": "application/ld+json",
        "endpoints": {
            "POST /api/files": "upload a file; returns metadata and preview",
            "GET /api/files/{id}": "metadata again",
            "GET /api/files/{id}/preview?rows=N": "first N rows or parsed entities",
            "POST /api/files/{id}/generate": "generate converted JSON-LD as a download",
            "POST /api/files/{id}/output": "regenerate preview JSON-LD as JSON",
            "PUT /api/files/{id}/roles": "update roles",
            "POST /api/files/{id}/variables": "add a variable",
            "PATCH /api/files/{id}/variables/{name}": "edit variable metadata",
            "DELETE /api/files/{id}/variables/{name}": "remove a variable",
            "DELETE /api/files/{id}": "remove upload session",
            "POST /api/convert": "one-shot upload + generate (compatible with the DDICDI API)",
        },
        "authentication": "X-API-Key header" if settings.api_key else "none",
    }


# -- session style --------------------------------------------------------------------


@router.post("/files", response_model=FileInfo, dependencies=[Depends(require_api_key)])
async def upload(
    file: UploadFile = File(...),
    preview_rows: int = Query(settings.default_max_rows, ge=0, le=1000),
    target_format: str = Query("cdif", description="Target format: cdif, croissant, soso, rocrate"),
    store: UploadStore = Depends(get_store),
) -> FileInfo:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type {ext!r}")

    content = await file.read()
    content_str = content.decode("utf-8", errors="replace")

    # Detect format
    src_path = Path(file.filename or "upload")
    detected_fmt = detect_file_format(src_path, content_str)

    # Extract initial variable information and labels
    try:
        parsed_doc = json.loads(content_str) if content_str.strip().startswith(("{", "[")) else {}
    except Exception:
        parsed_doc = {}

    variables_list, preview_list, file_label = extract_variables_and_preview(parsed_doc)

    meta_dict = {
        "filename": file.filename or "upload",
        "file_format": detected_fmt,
        "target_format": target_format,
        "number_rows": len(preview_list),
        "number_variables": len(variables_list),
        "encoding": "utf-8",
        "file_label": file_label,
        "delimiter": None,
        "sentinels_in_data": False,
        "variables": variables_list,
        "preview": preview_list,
    }

    file_id, _ = store.create(file.filename or "upload", content, meta_dict)
    store.cleanup_expired()

    return FileInfo(
        file_id=file_id,
        filename=meta_dict["filename"],
        file_format=detected_fmt,
        detected_flavor=detected_fmt,
        target_format=target_format,
        number_rows=len(preview_list),
        number_variables=len(variables_list),
        encoding="utf-8",
        file_label=file_label,
        variables=[VariableOut(**v) for v in variables_list],
        preview=preview_list[:preview_rows],
    )


@router.get("/files/{file_id}", response_model=FileInfo, dependencies=[Depends(require_api_key)])
def file_info(
    file_id: str,
    preview_rows: int = Query(0, ge=0, le=1000),
    store: UploadStore = Depends(get_store),
) -> FileInfo:
    meta = _load_meta(store, file_id)
    vars_out = [VariableOut(**v) for v in meta.get("variables", [])]
    return FileInfo(
        file_id=file_id,
        filename=meta.get("filename", "upload"),
        file_format=meta.get("file_format", "unknown"),
        detected_flavor=meta.get("file_format"),
        target_format=meta.get("target_format", "cdif"),
        number_rows=meta.get("number_rows", 0),
        number_variables=len(vars_out),
        encoding=meta.get("encoding", "utf-8"),
        file_label=meta.get("file_label"),
        variables=vars_out,
        preview=meta.get("preview", [])[:preview_rows],
    )


@router.get("/files/{file_id}/preview", dependencies=[Depends(require_api_key)])
def preview(
    file_id: str,
    rows: int = Query(5, ge=0, le=10000),
    offset: int = Query(0, ge=0),
    store: UploadStore = Depends(get_store),
) -> dict:
    meta = _load_meta(store, file_id)
    all_rows = meta.get("preview", [])
    sliced = all_rows[offset : offset + rows] if all_rows else []
    return {
        "columns": [v["name"] for v in meta.get("variables", [])],
        "rows": sliced,
        "offset": offset,
        "total_rows": len(all_rows),
    }


@router.post("/files/{file_id}/generate", dependencies=[Depends(require_api_key)])
def generate(
    file_id: str,
    req: GenerateRequest,
    store: UploadStore = Depends(get_store),
) -> Response:
    meta = _load_meta(store, file_id)
    target_format = req.target_format or meta.get("target_format", "cdif")
    try:
        output_doc = _execute_conversion(store, file_id, target_format)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Conversion error: {exc}")

    output_str = json.dumps(output_doc, indent=2, ensure_ascii=False)
    return _download(output_str, meta.get("filename", "upload"), target_format)


@router.post("/files/{file_id}/output", dependencies=[Depends(require_api_key)])
def output(
    file_id: str,
    req: OutputRequest,
    store: UploadStore = Depends(get_store),
) -> Response:
    meta = _load_meta(store, file_id)
    target_format = req.target_format or meta.get("target_format", "cdif")
    try:
        output_doc = _execute_conversion(store, file_id, target_format)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Conversion error: {exc}")

    output_str = json.dumps(output_doc, indent=2, ensure_ascii=False)
    return Response(content=output_str, media_type="application/ld+json")


# -- editing variables ----------------------------------------------------------------


@router.put("/files/{file_id}/roles", response_model=FileInfo, dependencies=[Depends(require_api_key)])
def put_roles(file_id: str, body: RolesIn, store: UploadStore = Depends(get_store)) -> FileInfo:
    meta = _load_meta(store, file_id)
    roles = body.roles
    for v in meta.get("variables", []):
        if v["name"] in roles:
            v["default_role"] = roles[v["name"]]
    store.save_meta(file_id, meta)
    return file_info(file_id, preview_rows=0, store=store)


@router.post(
    "/files/{file_id}/variables", response_model=VariableOut, status_code=201, dependencies=[Depends(require_api_key)]
)
def add_variable(file_id: str, body: NewVariableIn, store: UploadStore = Depends(get_store)) -> VariableOut:
    meta = _load_meta(store, file_id)
    new_v = {
        "name": body.name,
        "label": body.label,
        "format": body.format,
        "type": body.type,
        "measure": body.measure,
        "numeric": False,
        "value_labels": body.value_labels,
        "missing": body.missing,
        "default_role": body.role,
        "unit_of_measure": body.unit_of_measure,
        "concepts": body.concepts,
        "functions": body.functions,
    }
    meta.setdefault("variables", []).append(new_v)
    store.save_meta(file_id, meta)
    return VariableOut(**new_v)


@router.patch(
    "/files/{file_id}/variables/{name}", response_model=VariableOut, dependencies=[Depends(require_api_key)]
)
def patch_variable(
    file_id: str, name: str, body: VariablePatchIn, store: UploadStore = Depends(get_store)
) -> VariableOut:
    meta = _load_meta(store, file_id)
    vars_list = meta.get("variables", [])
    found = None
    for v in vars_list:
        if v["name"] == name:
            found = v
            break
    if not found:
        raise HTTPException(status_code=404, detail=f"Variable '{name}' not found")

    patch_dict = body.model_dump(exclude_unset=True)
    if "new_name" in patch_dict and patch_dict["new_name"]:
        found["name"] = patch_dict["new_name"]
    if "role" in patch_dict:
        found["default_role"] = patch_dict["role"]
    for k in ["label", "format", "type", "measure", "value_labels", "missing", "unit_of_measure", "concepts", "functions"]:
        if k in patch_dict:
            found[k] = patch_dict[k]

    store.save_meta(file_id, meta)
    return VariableOut(**found)


@router.delete("/files/{file_id}/variables/{name}", response_model=FileInfo, dependencies=[Depends(require_api_key)])
def delete_variable(file_id: str, name: str, store: UploadStore = Depends(get_store)) -> FileInfo:
    meta = _load_meta(store, file_id)
    meta["variables"] = [v for v in meta.get("variables", []) if v["name"] != name]
    store.save_meta(file_id, meta)
    return file_info(file_id, preview_rows=0, store=store)


@router.delete("/files/{file_id}", status_code=204, dependencies=[Depends(require_api_key)])
def delete_file(file_id: str, store: UploadStore = Depends(get_store)) -> Response:
    store.delete(file_id)
    return Response(status_code=204)


# -- one-shot conversion endpoint (DDICDI API compatible) --------------------------------


@router.post("/convert", dependencies=[Depends(require_api_key)])
async def convert_once(
    file: UploadFile = File(...),
    target_format: str = Form("cdif"),
    store: UploadStore = Depends(get_store),
) -> Response:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type {ext!r}")

    content = await file.read()
    content_str = content.decode("utf-8", errors="replace")
    detected_fmt = detect_file_format(Path(file.filename or "upload"), content_str)

    meta_dict = {
        "filename": file.filename or "upload",
        "file_format": detected_fmt,
        "target_format": target_format,
        "number_rows": 0,
        "number_variables": 0,
    }

    file_id, _ = store.create(file.filename or "upload", content, meta_dict)
    try:
        output_doc = _execute_conversion(store, file_id, target_format)
        output_str = json.dumps(output_doc, indent=2, ensure_ascii=False)
        return _download(output_str, file.filename or "upload", target_format)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Conversion error: {exc}")
    finally:
        store.delete(file_id)
