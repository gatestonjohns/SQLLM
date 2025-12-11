import reflex as rx
from sqllm.state import State


def total_usage_component() -> rx.Component:
    """
    A component that displays the total token usage and cost for the current session.
    Reads from State.total_token_usage.
    """
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("activity", size=20, color="green"),
                rx.heading("Total Session Usage", size="3", weight="bold", color="green"),
                spacing="2",
                align="center",
            ),
            rx.hstack(
                # Input Tokens
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("arrow-down", size=16, color="blue"),
                            rx.text("Input Tokens", color="blue", size="2", weight="medium"),
                            spacing="1",
                            align="center",
                        ),
                        rx.text(
                            State.total_token_usage.input_tokens, 
                            weight="bold", 
                            size="3",
                            color="blue"
                        ),
                        align_items="center",
                        spacing="2",
                    ),
                    variant="surface",
                    color_scheme="blue",
                    size="1",
                    width="100%",
                ),
                # Output Tokens
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("arrow-up", size=16, color="purple"),
                            rx.text("Output Tokens", color="purple", size="2", weight="medium"),
                            spacing="1",
                            align="center",
                        ),
                        rx.text(
                            State.total_token_usage.output_tokens, 
                            weight="bold", 
                            size="3",
                            color="purple"
                        ),
                        align_items="center",
                        spacing="2",
                    ),
                    variant="surface",
                    color_scheme="purple",
                    size="1",
                    width="100%",
                ),
                # Total Tokens
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("zap", size=16, color="orange"),
                            rx.text("Total Tokens", color="orange", size="2", weight="medium"),
                            spacing="1",
                            align="center",
                        ),
                        rx.text(
                            State.total_token_usage.total_tokens, 
                            weight="bold", 
                            size="3",
                            color="orange"
                        ),
                        align_items="center",
                        spacing="2",
                    ),
                    variant="surface",
                    color_scheme="orange",
                    size="1",
                    width="100%",
                ),
                # Cost
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("dollar-sign", size=16, color="green"),
                            rx.text("Est. Cost", color="green", size="2", weight="medium"),
                            spacing="1",
                            align="center",
                        ),
                        rx.text(
                            f"${State.total_token_usage.cost:.2f}",
                            weight="bold",
                            size="3",
                            color="green"
                        ),
                        align_items="center",
                        spacing="2",
                    ),
                    variant="surface",
                    color_scheme="green",
                    size="1",
                    width="100%",
                ),
                columns="4",
                spacing="3",
                width="100%",
            ),
            spacing="4",
            width="100%",
        ),
        size="2",
        width="33%",
        variant="surface",
        height="100%",
    )
