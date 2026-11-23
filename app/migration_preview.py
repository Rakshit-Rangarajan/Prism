"""Fail-closed, side-effect-free synthetic tabular migration preview.

This module never connects to source/target systems or writes migrated records.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
import re

MAX_TEXT_LENGTH = 4096
MAX_FIELD_NAME_LENGTH = 128
SUPPORTED = frozenset({"text", "integer", "decimal", "boolean"})
INTEGER = re.compile(r"^[+-]?[0-9]+$")
DECIMAL = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?$")

@dataclass(frozen=True)
class FieldMap:
    source: str
    target: str
    target_type: str
    required: bool = True

def _convert(value: Any, kind: str) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list, tuple, set)):
        raise ValueError("nested values are unsupported")
    if kind == "text":
        text = str(value)
        if len(text) > MAX_TEXT_LENGTH:
            raise ValueError("text value exceeds 4096 characters")
        return text
    if kind == "integer":
        if isinstance(value, bool) or not INTEGER.fullmatch(str(value).strip()):
            raise ValueError("invalid integer")
        return int(str(value).strip())
    if kind == "decimal":
        if isinstance(value, bool) or not DECIMAL.fullmatch(str(value).strip()):
            raise ValueError("invalid decimal")
        try:
            parsed = Decimal(str(value).strip())
        except InvalidOperation:
            raise ValueError("invalid decimal") from None
        if not parsed.is_finite():
            raise ValueError("non-finite decimal")
        return str(parsed)
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        lookup = {"true": True, "false": False, "1": True, "0": False, "yes": True, "no": False}
        result = lookup.get(str(value).strip().lower())
        if result is None:
            raise ValueError("invalid boolean")
        return result
    raise ValueError("unsupported type")

def preview_migration(rows: list[dict[str, Any]], mappings: list[FieldMap], *, max_rows: int = 1000) -> dict[str, Any]:
    """Validate a bounded synthetic sample; return no partial output on failure."""
    if not isinstance(rows, list) or len(rows) > max_rows or max_rows < 1:
        raise ValueError("invalid or oversized sample")
    if not mappings or len(mappings) > 100:
        raise ValueError("mapping count must be 1..100")
    if len({m.target for m in mappings}) != len(mappings):
        raise ValueError("duplicate target fields")
    if any(not isinstance(m, FieldMap) or not isinstance(m.source, str) or not isinstance(m.target, str)
           or not m.source.strip() or not m.target.strip()
           or len(m.source) > MAX_FIELD_NAME_LENGTH or len(m.target) > MAX_FIELD_NAME_LENGTH
           or m.target_type not in SUPPORTED or not isinstance(m.required, bool) for m in mappings):
        raise ValueError("invalid field mapping")
    output, errors = [], []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append({"row": index, "field": None, "reason": "row is not an object"})
            continue
        converted = {}
        row_errors = []
        for mapping in mappings:
            if mapping.source not in row:
                row_errors.append({"row": index, "field": mapping.target, "reason": "source field missing"})
                continue
            try:
                value = _convert(row[mapping.source], mapping.target_type)
                if mapping.required and value is None:
                    raise ValueError("required value missing")
                converted[mapping.target] = value
            except ValueError as exc:
                row_errors.append({"row": index, "field": mapping.target, "reason": str(exc)})
        if row_errors:
            errors.extend(row_errors)
        else:
            output.append(converted)
    return {"synthetic": True, "mode": "dry-run", "source_count": len(rows),
            "valid_count": len(output), "invalid_count": len({e["row"] for e in errors}),
            "records": output, "errors": errors, "writes_performed": False}
