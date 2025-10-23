from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Any, Callable
import sqlglot


@dataclass
class VTFCall:
    """Description of a single virtual table function invocation discovered in the SQL AST."""

    handler: "VirtualTableFunction"
    args: list[Any]
    rewrite_to_table: Callable[[str], None]


class VirtualTableFunction(Protocol):
    """Contract for virtual table functions that can discover and materialize SQL table expressions."""

    function_name: str

    def discover(self, tree: sqlglot.Expression) -> list[VTFCall]:
        """Traverse the parsed SQL tree and return every invocation of this VTF as `VTFCall` objects."""

    def materialize(self, call: VTFCall, engine) -> str:
        """Create or reuse the physical table backing `call` and return the replacement table name."""
