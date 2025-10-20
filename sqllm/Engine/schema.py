from __future__ import annotations
from dataclasses import dataclass
from typing import List
import re

_DUCK_TYPES = {
    "TEXT",
    "VARCHAR",
    "INTEGER",
    "BIGINT",
    "DOUBLE",
    "BOOLEAN",
    "DATE",
    "TIMESTAMP",
}


@dataclass
class ColumnSpec:
    name: str
    duckdb_type: str


@dataclass
class SchemaSpec:
    columns: List[ColumnSpec]
    canonical: str
    pandas_dtypes: dict[str, str]
    table_name: str | None = None


_TABLE_PATTERN = re.compile(
    r"(?is)\s*(?:create\s+)?table\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*"
)


def _strip_table_wrapper(spec: str) -> tuple[str, str | None]:
    match = _TABLE_PATTERN.match(spec)
    if match:
        return match.group(2), match.group(1)
    return spec, None


def parse_schema_grammar(spec: str) -> SchemaSpec:
    # supports either "col type, ..." or "TABLE name (col type, ...)"
    inner, table_name = _strip_table_wrapper(spec.strip())
    cols: List[ColumnSpec] = []
    pandas_map: dict[str, str] = {}
    parts = [p.strip() for p in inner.split(",") if p.strip()]
    for p in parts:
        name, ty = p.split(None, 1)
        tnorm = ty.upper().replace("INT ", "INTEGER ").replace("INT", "INTEGER")
        tnorm = tnorm.replace("VARCHAR", "TEXT")
        tnorm = tnorm.replace("FLOAT", "DOUBLE")
        tmain = tnorm.split("(")[0].strip()
        if tmain not in _DUCK_TYPES:
            raise ValueError(f"Unsupported type: {ty}")
        cols.append(ColumnSpec(name=name, duckdb_type=tnorm))
        pandas_map[name] = _to_pandas_dtype(tmain)
    canonical = ",".join([f"{c.name} {c.duckdb_type}" for c in cols])
    return SchemaSpec(
        columns=cols,
        canonical=canonical,
        pandas_dtypes=pandas_map,
        table_name=table_name,
    )


def _to_pandas_dtype(t: str) -> str:
    if t in ("TEXT", "VARCHAR"):
        return "string"
    if t in ("INTEGER", "BIGINT"):
        return "Int64"
    if t == "DOUBLE":
        return "float64"
    if t == "BOOLEAN":
        return "boolean"
    if t in ("DATE", "TIMESTAMP"):
        return "string"
    return "string"


def build_json_schema(schema: SchemaSpec) -> dict:
    props = {}
    required = []
    for c in schema.columns:
        props[c.name] = {"type": _json_type_for(c.duckdb_type)}
        required.append(c.name)
    return {
        "name": "TableRows",
        "schema": {
            "type": "object",
            "properties": {
                "rows": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": props,
                        "required": required,
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["rows"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _json_type_for(t: str) -> str:
    t = t.split("(")[0].upper()
    if t in ("TEXT", "VARCHAR"):
        return "string"
    if t in ("INTEGER", "BIGINT", "DOUBLE"):
        return "number"
    if t == "BOOLEAN":
        return "boolean"
    if t in ("DATE", "TIMESTAMP"):
        return "string"
    return "string"
