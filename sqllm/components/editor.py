import reflex as rx
from reflex_monaco import monaco
from ..state import State

DEFAULT_SQL_QUERY = (
    "SELECT llm('What is the color of the sky in hexadecimal?') as sky_color_hex;"
)


class EditorState(rx.State):
    """State management for the raw SQL query editor."""

    sql_query: str = DEFAULT_SQL_QUERY

    @rx.event
    async def run_query(self):
        """Run the query using global state event handler."""
        return State.execute_query(self.sql_query)

    @rx.event
    def set_sql_query(self, sql_query: str):
        """Set the SQL query."""
        self.sql_query = sql_query


def editor_section() -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.hstack(
                    rx.icon("terminal", size=20, color="orange"),
                    rx.text(
                        "SQL Query Editor",
                        size="4",
                        weight="bold",
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.button(
                    rx.icon("play", size=18),
                    "Run Query",
                    on_click=EditorState.run_query.debounce(1000),
                    size="3",
                    color_scheme="indigo",
                    variant="solid",
                    cursor="pointer",
                ),
                spacing="2",
                align="center",
                justify="between",
                width="100%",
            ),
            rx.box(
                monaco(
                    default_language="sql",
                    value=EditorState.sql_query,
                    on_change=EditorState.set_sql_query.debounce(1000),
                    height="400px",
                    width="100%",
                ),
                height="400px",
                width="100%",
            ),
            spacing="3",
        ),
        variant="classic",
        width="100%",
    )
