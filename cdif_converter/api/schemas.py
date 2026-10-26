"""Pydantic request and response schemas matching DDICDI_generator_gen2 patterns."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class HealthOut(BaseModel):
    status: str
    version: str
    service: str


class VariableOut(BaseModel):
    name: str
    label: str | None = None
    format: str = "string"
    type: str = "string"
    measure: str = "nominal"
    numeric: bool = False
    value_labels: dict[str, str] = Field(default_factory=dict)
    missing: list[dict[str, Any]] = Field(default_factory=list)
    default_role: str = "measure"
    unit_of_measure: str | None = None
    concepts: list[dict[str, str]] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)


class FileInfo(BaseModel):
    file_id: str
    filename: str
    file_format: str
    detected_flavor: str | None = None
    target_format: str = "cdif"
    number_rows: int = 0
    number_variables: int = 0
    encoding: str | None = "utf-8"
    file_label: str | None = None
    delimiter: str | None = None
    sentinels_in_data: bool = False
    variables: list[VariableOut] = Field(default_factory=list)
    preview: list[dict[str, Any]] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    target_format: str = Field(
        "cdif",
        description="Target format: cdif, croissant, soso, rocrate, dcat, fair2"
    )
    roles: dict[str, str] = Field(default_factory=dict)
    max_rows: int = Field(5, ge=0)
    process_all_rows: bool = False
    include_statistics: bool = False
    statistics_weight: str | None = None
    statistics_include: list[str] | None = None


class OutputRequest(BaseModel):
    target_format: str = Field("cdif")
    max_rows: int = Field(5, ge=0)
    process_all_rows: bool = False
    include_statistics: bool = False


class RolesIn(BaseModel):
    roles: dict[str, str] = Field(default_factory=dict)


class VariablePatchIn(BaseModel):
    label: str | None = None
    format: str | None = None
    type: str | None = None
    measure: str | None = None
    value_labels: dict[str, str] | None = None
    missing: list[dict[str, Any]] | None = None
    role: str | None = None
    new_name: str | None = None
    unit_of_measure: str | None = None
    concepts: list[dict[str, Any]] | None = None
    functions: list[str] | None = None


class NewVariableIn(BaseModel):
    name: str
    label: str | None = None
    format: str = "string"
    type: str = "string"
    measure: str = "nominal"
    value_labels: dict[str, str] = Field(default_factory=dict)
    missing: list[dict[str, Any]] = Field(default_factory=list)
    role: str = "measure"
    fill: str | None = None
    fill_value: str | None = None
    position: int | None = None
    unit_of_measure: str | None = None
    concepts: list[dict[str, Any]] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)
