import json
import re
from dataclasses import dataclass
from enum import Enum

# SAMPLE TABLE DEF STR:

# TABLE name WITH COLUMNS [{"name": "col_name1", "type": "type1", "description": "description1", "pattern": "pattern1"}, {...}]


class DataType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"


DATA_TYPE_TO_DUCKDB_TYPE = {
    DataType.STRING: "VARCHAR",
    DataType.NUMBER: "DOUBLE",
    DataType.INTEGER: "BIGINT",
    DataType.BOOLEAN: "BOOLEAN",
}

DATA_TYPE_TO_PANDAS_DTYPE = {
    DataType.STRING: "string",
    DataType.NUMBER: "float",
    DataType.INTEGER: "int",
    DataType.BOOLEAN: "bool",
}


@dataclass
class ColumnSpec:
    name: str
    type: DataType
    description: str | None = None
    pattern: str | None = None


@dataclass
class SchemaSpec:
    table_name: str | None
    columns: list[ColumnSpec]


def parse_schema_grammar(schema_str: str) -> SchemaSpec:
    """
    Parse a schema string into a SchemaSpec object.
    Schema string syntax: "TABLE name WITH COLUMNS [{"name": "col_name1", "type": "type1", "description": "description1", "pattern": "pattern1"}, {...}]"

    Args:
        schema_str: The schema string to parse

    Returns:
        A SchemaSpec object containing table name and column specifications
    """
    if not schema_str or not isinstance(schema_str, str):
        raise ValueError("Schema string cannot be empty or None")

    schema_str = schema_str.strip()

    # Match the pattern: TABLE name WITH COLUMNS [...]
    pattern = r"^TABLE\s+(\w+)\s+WITH\s+COLUMNS\s+(\[.*\])$"
    match = re.match(pattern, schema_str, re.IGNORECASE)

    if not match:
        raise ValueError(
            f"Malformed schema string. Expected format: 'TABLE name WITH COLUMNS [...]', got: {schema_str}"
        )

    table_name = match.group(1)
    columns_json_str = match.group(2)

    try:
        columns_data = json.loads(columns_json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in columns specification: {e}")

    if not isinstance(columns_data, list):
        raise ValueError("Columns specification must be a JSON array")

    if not columns_data:
        raise ValueError("Columns specification cannot be empty")

    columns = []
    for i, col_data in enumerate(columns_data):
        if not isinstance(col_data, dict):
            raise ValueError(f"Column {i} must be a JSON object")

        if "name" not in col_data:
            raise ValueError(f"Column {i} missing required 'name' field")

        if "type" not in col_data:
            raise ValueError(f"Column {i} missing required 'type' field")

        col_name = col_data["name"]
        col_type_str = col_data["type"]

        if not isinstance(col_name, str) or not col_name.strip():
            raise ValueError(f"Column {i} name must be a non-empty string")

        try:
            col_type = DataType(col_type_str)
        except ValueError:
            valid_types = [dt.value for dt in DataType]
            raise ValueError(
                f"Column {i} has invalid type '{col_type_str}'. Valid types: {valid_types}"
            )

        description = col_data.get("description")
        pattern = col_data.get("pattern")

        if description is not None and not isinstance(description, str):
            raise ValueError(f"Column {i} description must be a string")

        if pattern is not None and not isinstance(pattern, str):
            raise ValueError(f"Column {i} pattern must be a string")

        columns.append(
            ColumnSpec(
                name=col_name.strip(),
                type=col_type,
                description=description,
                pattern=pattern,
            )
        )

    return SchemaSpec(table_name=table_name, columns=columns)


def build_table_json_schema(schema_spec: SchemaSpec) -> dict:
    """
    Build a JSON schema from a SchemaSpec object that is compatible with LLM API output schema format.

    Args:
        schema_spec: The SchemaSpec object to build a JSON schema from

    Returns:
        A JSON schema compatible with LLM API output schema format for an array of table rows
    """
    # Build properties for each column, only including description/pattern if they are not None
    column_properties = {}
    for col in schema_spec.columns:
        col_schema = {"type": col.type.value}
        if col.description is not None:
            col_schema["description"] = col.description
        if col.pattern is not None:
            col_schema["pattern"] = col.pattern
        column_properties[col.name] = col_schema

    # Return schema for an array of table rows
    return {
        "name": schema_spec.table_name,
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "rows": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": column_properties,
                        "required": [col.name for col in schema_spec.columns],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["rows"],
            "additionalProperties": False,
        },
    }


def build_row_json_schema(schema_spec: SchemaSpec) -> dict:
    """
    Build a JSON schema from a SchemaSpec object for a single row object.

    Args:
        schema_spec: The SchemaSpec object to build a JSON schema from

    Returns:
        A JSON schema compatible with LLM API output schema format for a single table row
    """
    # Build properties for each column, only including description/pattern if they are not None
    column_properties = {}
    for col in schema_spec.columns:
        col_schema = {"type": col.type.value}
        if col.description is not None:
            col_schema["description"] = col.description
        if col.pattern is not None:
            col_schema["pattern"] = col.pattern
        column_properties[col.name] = col_schema

    return {
        "name": schema_spec.table_name,
        "strict": True,
        "schema": {
            "type": "object",
            "properties": column_properties,
            "required": [col.name for col in schema_spec.columns],
            "additionalProperties": False,
        },
    }
