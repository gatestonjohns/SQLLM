import reflex as rx


class TokenUsage(rx.Base):
    """
    Class to track token usage and cost.

    Semantics:
    - Instances returned by LLMProvider methods are "snapshots" of a single call.
    - The instance stored in `sqllm.backend.LLM.context` is a "mutable accumulator"
      for the entire execution.
    - Use `+=` (in-place add) to update the accumulator.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0

    def __iadd__(self, other: "TokenUsage") -> "TokenUsage":
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.total_tokens += other.total_tokens
        self.cost += other.cost
        return self

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cost=self.cost + other.cost,
        )
