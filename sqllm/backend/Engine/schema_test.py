import pytest
from sqllm.backend.Engine.schema import (
    DataType,
    ColumnSpec,
    SchemaSpec,
    parse_schema_grammar,
    build_table_json_schema,
    build_row_json_schema,
    DATA_TYPE_TO_DUCKDB_TYPE,
    DATA_TYPE_TO_PANDAS_DTYPE,
)


class TestDataType:
    def test_mappings_exist(self):
        """Test that all DataType values have mappings to DuckDB and Pandas types."""
        for data_type in DataType:
            assert data_type in DATA_TYPE_TO_DUCKDB_TYPE
            assert data_type in DATA_TYPE_TO_PANDAS_DTYPE


class TestParseSchemaGrammar:
    def test_valid_basic_schema(self):
        schema_str = 'TABLE my_table WITH COLUMNS [{"name": "id", "type": "integer"}, {"name": "name", "type": "string", "pattern": "^[A-Za-z]+$"}]'
        schema = parse_schema_grammar(schema_str)

        assert schema.table_name == "my_table"
        assert len(schema.columns) == 2

        assert schema.columns[0].name == "id"
        assert schema.columns[0].type == DataType.INTEGER
        assert schema.columns[0].description is None
        assert schema.columns[0].pattern is None

        assert schema.columns[1].name == "name"
        assert schema.columns[1].type == DataType.STRING
        assert schema.columns[1].description is None
        assert schema.columns[1].pattern == "^[A-Za-z]+$"

    def test_valid_full_schema(self):
        id_col_description = "User ID"
        id_col_pattern = "^\\\\d+$"

        schema_str = (
            "TABLE users WITH COLUMNS ["
            f'{{"name": "id", "type": "integer", "description": "{id_col_description}", "pattern": "{id_col_pattern}"}}, '
            '{"name": "is_active", "type": "boolean"}'
            "]"
        )
        schema = parse_schema_grammar(schema_str)

        assert schema.table_name == "users"
        assert len(schema.columns) == 2

        id_col = schema.columns[0]
        assert id_col.name == "id"
        assert id_col.type == DataType.INTEGER
        assert id_col.description == "User ID"
        assert id_col.pattern == "^\\d+$"

        is_active_col = schema.columns[1]
        assert is_active_col.name == "is_active"
        assert is_active_col.type == DataType.BOOLEAN
        assert is_active_col.description is None
        assert is_active_col.pattern is None

    def test_empty_input(self):
        with pytest.raises(ValueError, match="Schema string cannot be empty"):
            parse_schema_grammar("")
        with pytest.raises(ValueError, match="Schema string cannot be empty"):
            parse_schema_grammar(None)

    def test_malformed_string(self):
        with pytest.raises(ValueError, match="Malformed schema string"):
            parse_schema_grammar("NOT A VALID SCHEMA")
        with pytest.raises(ValueError, match="Malformed schema string"):
            parse_schema_grammar("TABLE users COLUMNS []")  # Missing WITH

    def test_invalid_json(self):
        schema_str = "TABLE users WITH COLUMNS [{invalid_json}]"
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_schema_grammar(schema_str)

    def test_malformed_no_brackets(self):
        # Case 1: No square brackets -> Regex fails
        schema_str = "TABLE users WITH COLUMNS {}"
        with pytest.raises(ValueError, match="Malformed schema string"):
            parse_schema_grammar(schema_str)

    def test_column_missing_fields(self):
        # Case 2: valid brackets, but empty column object -> Validation fails
        schema_str = "TABLE users WITH COLUMNS [{}]"
        with pytest.raises(ValueError, match="Column 0 missing required 'name' field"):
            parse_schema_grammar(schema_str)

    def test_empty_columns(self):
        schema_str = "TABLE users WITH COLUMNS []"
        with pytest.raises(ValueError, match="Columns specification cannot be empty"):
            parse_schema_grammar(schema_str)

    def test_invalid_column_structure(self):
        # Not a dict
        with pytest.raises(ValueError, match="must be a JSON object"):
            parse_schema_grammar('TABLE users WITH COLUMNS ["string_not_obj"]')

        # Missing name
        with pytest.raises(ValueError, match="missing required 'name' field"):
            parse_schema_grammar('TABLE users WITH COLUMNS [{"type": "string"}]')

        # Missing type
        with pytest.raises(ValueError, match="missing required 'type' field"):
            parse_schema_grammar('TABLE users WITH COLUMNS [{"name": "id"}]')

    def test_invalid_data_values(self):
        # Empty name
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            parse_schema_grammar(
                'TABLE users WITH COLUMNS [{"name": "", "type": "string"}]'
            )

        # Invalid type enum
        with pytest.raises(ValueError, match="has invalid type"):
            parse_schema_grammar(
                'TABLE users WITH COLUMNS [{"name": "id", "type": "invalid_type"}]'
            )

        # Invalid description type
        with pytest.raises(ValueError, match="description must be a string"):
            parse_schema_grammar(
                'TABLE users WITH COLUMNS [{"name": "id", "type": "string", "description": 123}]'
            )

        # Invalid pattern type
        with pytest.raises(ValueError, match="pattern must be a string"):
            parse_schema_grammar(
                'TABLE users WITH COLUMNS [{"name": "id", "type": "string", "pattern": 123}]'
            )


class TestBuildTableJsonSchema:
    def test_build_schema_basic(self):
        spec = SchemaSpec(
            table_name="test_table",
            columns=[
                ColumnSpec(name="col1", type=DataType.STRING),
                ColumnSpec(name="col2", type=DataType.INTEGER),
            ],
        )

        json_schema = build_table_json_schema(spec)

        assert json_schema["name"] == "test_table"
        assert json_schema["strict"] is True
        assert json_schema["schema"]["type"] == "object"
        assert json_schema["schema"]["additionalProperties"] is False
        assert json_schema["schema"]["required"] == ["rows"]

        rows = json_schema["schema"]["properties"]["rows"]
        assert rows["type"] == "array"

        items = rows["items"]
        assert items["type"] == "object"
        assert items["additionalProperties"] is False
        assert set(items["required"]) == {"col1", "col2"}

        props = items["properties"]
        assert props["col1"] == {"type": "string"}
        assert props["col2"] == {"type": "integer"}

    def test_build_schema_with_details(self):
        spec = SchemaSpec(
            table_name="test_table",
            columns=[
                ColumnSpec(
                    name="detailed",
                    type=DataType.STRING,
                    description="A description",
                    pattern="^test$",
                ),
            ],
        )

        json_schema = build_table_json_schema(spec)
        props = json_schema["schema"]["properties"]["rows"]["items"]["properties"]

        assert props["detailed"]["description"] == "A description"
        assert props["detailed"]["pattern"] == "^test$"


class TestBuildRowJsonSchema:
    def test_build_row_schema_basic(self):
        spec = SchemaSpec(
            table_name="test_table",
            columns=[
                ColumnSpec(name="col1", type=DataType.STRING),
                ColumnSpec(name="col2", type=DataType.INTEGER),
            ],
        )

        json_schema = build_row_json_schema(spec)

        assert json_schema["name"] == "test_table"
        assert json_schema["strict"] is True
        assert json_schema["schema"]["type"] == "object"
        assert json_schema["schema"]["additionalProperties"] is False
        assert set(json_schema["schema"]["required"]) == {"col1", "col2"}

        props = json_schema["schema"]["properties"]
        assert props["col1"] == {"type": "string"}
        assert props["col2"] == {"type": "integer"}

    def test_build_row_schema_with_details(self):
        spec = SchemaSpec(
            table_name="test_table",
            columns=[
                ColumnSpec(
                    name="detailed",
                    type=DataType.STRING,
                    description="A description",
                    pattern="^test$",
                ),
            ],
        )

        json_schema = build_row_json_schema(spec)
        props = json_schema["schema"]["properties"]

        assert props["detailed"]["description"] == "A description"
        assert props["detailed"]["pattern"] == "^test$"
