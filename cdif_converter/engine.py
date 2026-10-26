"""Core conversion engine routing all supported formats to/from CDIF."""

from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

# Add subdirectories to sys.path so modules can load cleanly
for sub in [
    REPO_ROOT,
    REPO_ROOT / "croissant",
    REPO_ROOT / "soso",
    REPO_ROOT / "DCAT",
    REPO_ROOT / "DDI",
    REPO_ROOT / "DDI-CDI",
    REPO_ROOT / "ROCrate",
    REPO_ROOT / "UMM",
    REPO_ROOT / "FAIR2",
    REPO_ROOT / "validation",
]:
    p = str(sub)
    if p not in sys.path:
        sys.path.insert(0, p)


def detect_file_format(path: Path, content_str: str) -> str:
    """Detect whether file is croissant, soso, dcat, ddi, rocrate, umm, fair2, or cdif."""
    lower_name = path.name.lower()
    stripped = content_str.strip()

    if stripped.startswith("<") or lower_name.endswith(".xml"):
        return "ddi"

    if stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(stripped)
        except Exception:
            return "unknown"

        # Check RO-Crate
        if isinstance(data, dict) and "@graph" in data:
            for item in data["@graph"]:
                if item.get("@id") == "ro-crate-metadata.json":
                    return "rocrate"

        # Check Croissant
        context = data.get("@context", "") if isinstance(data, dict) else ""
        ctx_str = json.dumps(context)
        if "mlcommons.org/croissant" in ctx_str or "http://mlcommons.org/croissant" in ctx_str:
            return "croissant"

        # Check CDIF
        conforms = str(data.get("schema:subjectOf", {}).get("dcterms:conformsTo", "")) if isinstance(data, dict) else ""
        if "w3id.org/cdif" in conforms or "crossdomaininteroperability.org" in conforms:
            return "cdif"

        # Check FAIR2
        if "fair2" in lower_name or "fair2" in ctx_str:
            return "fair2"

        # Check UMM
        if isinstance(data, dict) and ("MetadataSpecification" in data or "EntryTitle" in data):
            return "umm"

        # Check DCAT
        types = str(data.get("@type", "")) if isinstance(data, dict) else ""
        if "dcat:Catalog" in types or "dcat:Dataset" in types or "dcat" in ctx_str:
            return "dcat"

        # Check SOSO / schema.org
        if "schema.org" in ctx_str or "schema.org" in str(data.get("@type", "")):
            return "soso"

    return "unknown"


def extract_variables_and_preview(doc: Any) -> Tuple[list[dict], list[dict], str | None]:
    """Extract variable metadata and preview rows from parsed JSON-LD."""
    variables = []
    preview = []
    file_label = None

    if isinstance(doc, dict):
        file_label = doc.get("name") or doc.get("schema:name") or doc.get("dcterms:title")

        # CDIF variableMeasured or Croissant RecordSet field
        var_measured = doc.get("schema:variableMeasured") or doc.get("variableMeasured") or []
        if isinstance(var_measured, list):
            for v in var_measured:
                if isinstance(v, dict):
                    vname = v.get("schema:name") or v.get("name") or v.get("@id", "var")
                    vlabel = v.get("schema:description") or v.get("description")
                    vtype = str(v.get("cdif:physicalDataType") or v.get("dataType") or "string")
                    variables.append({
                        "name": str(vname),
                        "label": str(vlabel) if vlabel else None,
                        "format": vtype,
                        "type": vtype,
                        "measure": "nominal",
                        "numeric": any(t in vtype.lower() for t in ["int", "float", "double", "num"]),
                        "value_labels": {},
                        "missing": [],
                        "default_role": "measure",
                        "unit_of_measure": None,
                        "concepts": [],
                        "functions": []
                    })

        # Croissant fields under recordSet
        rec_sets = doc.get("recordSet") or doc.get("cr:recordSet") or []
        if isinstance(rec_sets, list):
            for rs in rec_sets:
                if isinstance(rs, dict):
                    fields = rs.get("field") or rs.get("cr:field") or []
                    for f in fields:
                        if isinstance(f, dict):
                            fname = f.get("name") or f.get("cr:name") or f.get("@id", "field")
                            ftype = str(f.get("dataType") or f.get("cr:dataType") or "string")
                            variables.append({
                                "name": str(fname),
                                "label": str(f.get("description") or f.get("cr:description")),
                                "format": ftype,
                                "type": ftype,
                                "measure": "nominal",
                                "numeric": any(t in ftype.lower() for t in ["int", "float", "double", "num"]),
                                "value_labels": {},
                                "missing": [],
                                "default_role": "measure",
                                "unit_of_measure": None,
                                "concepts": [],
                                "functions": []
                            })

    return variables, preview, file_label


def convert_source_to_cdif(src_path: Path, src_format: str, content_str: str) -> dict:
    """Convert any source format into CDIF."""
    if src_format == "cdif":
        return json.loads(content_str)

    if src_format == "croissant":
        from ConvertFromCroissant import convert as convert_croissant
        data = json.loads(content_str)
        return convert_croissant(data, verbose=False)

    if src_format == "soso":
        from ConvertFromSOSO import convert_soso_to_cdif
        data = json.loads(content_str)
        return convert_soso_to_cdif(data)

    if src_format == "dcat":
        from dcat_to_cdif import convert_dcat_to_cdif
        data = json.loads(content_str)
        # Handle catalog vs dataset
        if "dcat:Dataset" in str(data.get("@type", "")):
            return convert_dcat_to_cdif(data)
        elif "@graph" in data:
            datasets = [n for n in data["@graph"] if "dcat:Dataset" in str(n.get("@type", ""))]
            if datasets:
                return convert_dcat_to_cdif(datasets[0], graph=data["@graph"])
            return convert_dcat_to_cdif(data["@graph"][0], graph=data["@graph"])
        return convert_dcat_to_cdif(data)

    if src_format == "ddi":
        from ddi2cdif import sniff_flavor
        flavor = sniff_flavor(src_path)
        if flavor in ("codebook-1.2.2", "codebook-2.5"):
            from ddi_sssom_to_cdif import convert as convert_codebook
            return convert_codebook(src_path)
        elif flavor == "ddi-cdi-xml":
            from ddicdi_to_cdif import convert as convert_ddicdi_xml
            return convert_ddicdi_xml(src_path)
        elif flavor == "ddi-cdi-jsonld":
            from ddicdi_jsonld_to_cdif import convert as convert_ddicdi_jsonld
            data = json.loads(content_str)
            return convert_ddicdi_jsonld(data)
        else:
            from ddi_sssom_to_cdif import convert as convert_codebook
            return convert_codebook(src_path)

    if src_format == "rocrate":
        from ROCrateToCDIF import convert_rocrate_to_cdif
        data = json.loads(content_str)
        return convert_rocrate_to_cdif(data, profile="discovery")

    if src_format == "umm":
        from umm_to_cdif import convert_collection
        data = json.loads(content_str)
        return convert_collection(data)

    if src_format == "fair2":
        from fair2_to_cdif import convert_fair2
        data = json.loads(content_str)
        return convert_fair2(data)

    # Fallback attempt via SOSO / Schema.org
    try:
        from ConvertFromSOSO import convert_soso_to_cdif
        return convert_soso_to_cdif(json.loads(content_str))
    except Exception as exc:
        raise ValueError(f"Unsupported conversion from format '{src_format}': {exc}")


def convert_cdif_to_target(cdif_data: dict, target_format: str) -> dict:
    """Convert a CDIF document into the requested target format."""
    target_format = target_format.lower().strip()
    if target_format in ("cdif", "cdif-discovery", "cdif-core", "jsonld"):
        return cdif_data

    if target_format == "croissant":
        from ConvertToCroissant import convert_cdif_to_croissant
        croissant, warnings = convert_cdif_to_croissant(cdif_data, verbose=False)
        return croissant

    if target_format == "soso":
        from ConvertToSOSO import convert_cdif_to_soso
        return convert_cdif_to_soso(cdif_data)

    if target_format == "rocrate":
        from ConvertToROCrate import convert_to_rocrate
        return convert_to_rocrate(cdif_data)

    raise ValueError(f"Target format '{target_format}' conversion from CDIF not supported.")
