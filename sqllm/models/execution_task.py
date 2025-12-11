from typing import Literal
import reflex as rx
import uuid
from pydantic.v1 import Field
from .token_usage import TokenUsage
from dataclasses import dataclass
import pandas as pd

ExecutionTaskType = Literal["EDITOR", "PDF_TO_TABLE", "SMART_JOIN", "SMART_JOIN_TEST"]


@dataclass(frozen=True)
class ExecResult:
    df: pd.DataFrame
    warnings: list[str]


class ExecutionTask(rx.Base):
    """
    A class that represents a single execution task for a given SQLLM input.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    sql: str
    summary: str
    type: ExecutionTaskType
    percent_done: int = 0
    result: ExecResult | None = None
    error: Exception | None = None
    warnings: list[str] = []
    usage: TokenUsage | None = None
