import contextvars
import logging
from typing import Optional
from ...models.token_usage import TokenUsage

# Context variable to hold the current execution's TokenUsage accumulator
_current_usage: contextvars.ContextVar[Optional[TokenUsage]] = contextvars.ContextVar(
    "current_usage", default=None
)


def init_usage() -> TokenUsage:
    """
    Initialize a fresh TokenUsage accumulator for the current context.
    Returns the new instance so the caller can retain a reference if needed.
    """
    usage = TokenUsage()
    _current_usage.set(usage)
    return usage


def get_usage() -> Optional[TokenUsage]:
    """
    Retrieve the current TokenUsage accumulator, or None if not set.
    """
    return _current_usage.get()


def accumulate_usage(new_usage: TokenUsage) -> None:
    """
    Add the provided usage to the current context's accumulator.
    If no accumulator is found (e.g., running in a thread without context),
    logs a warning.
    """
    accumulator = _current_usage.get()
    if accumulator is not None:
        accumulator += new_usage
    else:
        logging.warning(
            "Attempted to accumulate token usage, but no active execution context was found. "
            "This usage will be lost. (Are you running inside a UDF on a separate thread?)"
        )
