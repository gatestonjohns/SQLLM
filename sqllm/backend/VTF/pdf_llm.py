from __future__ import annotations
import logging
from typing import Any
from sqlglot import expressions as exp
from .base import VTFCall
from ..Engine.schema import parse_schema_grammar, build_table_json_schema
from ..workflows.pdftodf import pdf_to_dataframe


class LLMPDFToTableVTF:
    function_name = "llm_pdf_to_table"

    def discover(self, tree: exp.Expression) -> list[VTFCall]:
        calls: list[VTFCall] = []
        table_function_cls = getattr(exp, "TableFunction", None)
        for node in tree.walk(bfs=False):
            if isinstance(node, exp.Func) or (
                table_function_cls is not None and isinstance(node, table_function_cls)
            ):
                name = node.name.upper() if hasattr(node, "name") else ""
                if name == self.function_name.upper():
                    if not self._is_in_from_or_join(node):
                        raise ValueError("llm_pdf_to_table must be used in FROM/JOIN")
                    expressions_arg = node.args.get("expressions")
                    if expressions_arg is None:
                        exprs: list[Any] = []
                    elif isinstance(expressions_arg, (list, tuple)):
                        exprs = list(expressions_arg)
                    else:
                        exprs = [expressions_arg]

                    args = [self._literal_value(a) for a in exprs]
                    calls.append(
                        VTFCall(
                            handler=self,
                            args=args,
                            rewrite_to_table=lambda tbl, n=node: self._rewrite_node(
                                n, tbl
                            ),
                        )
                    )
        return calls

    async def materialize(self, call: VTFCall, engine, tracker=None) -> str:
        pdf_id, schema_str, prompt_text, options = self._parse_args(call.args)
        print(f"prompt text for pdf to table call: {prompt_text}")
        schema_spec = parse_schema_grammar(schema_str)
        table_json_schema = build_table_json_schema(schema_spec)
        table_name = engine._generate_new_table_name(pdf_id, ensure_new=False)

        existing_tables = engine._get_existing_table_names()
        table_exists = table_name in existing_tables
        force = bool(options.get("force_recreate", False))

        if not table_exists or force:
            df = await pdf_to_dataframe(
                llm=engine.llm,
                pdf_path=pdf_id,
                table_json_schema=table_json_schema,
                user_instructions=prompt_text or "",
                tracker=tracker,
            )
            engine._materialize_df(df, table_name)
        else:
            logging.debug("Reusing existing table %s for llm_pdf_to_table", table_name)

        call.rewrite_to_table(table_name)
        return table_name

    def _build_prompt(
        self,
        schema_spec,
        text: str,
        prompt_text: str | None,
    ) -> str:
        schema_desc = ", ".join(
            [f"{c.name} {c.duckdb_type}" for c in schema_spec.columns]
        )
        prompt_parts = [
            "Extract data from the following PDF text into the specified table schema.",
            f"Schema: {schema_desc}",
        ]
        if prompt_text:
            prompt_parts.append(f"Instruction: {prompt_text}")
        prompt_parts.append(
            "Return JSON matching the provided JSON Schema. Do not include prose. "
            f"Text:\n{text}"
        )
        return "\n".join(prompt_parts) + "\n"

    def _parse_args(
        self, args: list[Any]
    ) -> tuple[str, str, str | None, dict[str, Any]]:
        if len(args) < 2:
            raise ValueError(
                "llm_pdf_to_table requires (pdf_identifier, schema, [prompt], [options_json])"
            )
        pdf_id = args[0]
        schema_str = args[1]
        prompt_text: str | None = None
        options: dict[str, Any]

        if len(args) == 2:
            options = {}
        elif len(args) == 3 and isinstance(args[2], dict):
            options = args[2]
        else:
            prompt_text = args[2]
            options = args[3] if len(args) > 3 else {}

        if not isinstance(pdf_id, str) or not isinstance(schema_str, str):
            raise ValueError("Invalid argument types for llm_pdf_to_table")
        if prompt_text is not None and not isinstance(prompt_text, str):
            raise ValueError("Prompt text must be a string if provided")
        if not isinstance(options, dict):
            raise ValueError("Options argument must be a JSON object")
        return pdf_id, schema_str, prompt_text, options

    def _is_in_from_or_join(self, node) -> bool:
        p = node.parent
        while p is not None and not isinstance(p, exp.Select):
            if isinstance(p, (exp.Join, exp.From)):
                return True
            p = p.parent
        return isinstance(p, exp.Select)

    def _literal_value(self, e: exp.Expression) -> Any:
        if isinstance(e, exp.Literal):
            return e.this
        try:
            return e.this
        except Exception:
            raise ValueError("Arguments to llm_pdf_to_table must be literals")

    def _rewrite_node(self, node: exp.Expression, table_name: str) -> None:
        table_expr = exp.Table(this=exp.Identifier(this=table_name, quoted=False))
        node.replace(table_expr)
