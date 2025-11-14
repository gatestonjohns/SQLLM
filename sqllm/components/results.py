import pandas as pd
import reflex as rx
from sqllm.state import State


class ResultsState(rx.State):
    """State management for the results section."""

    export_dialog_open: bool = False
    export_filename: str = "query_results.csv"

    @rx.var
    async def results_df(self) -> pd.DataFrame:
        """Get the results dataframe."""
        return await self.get_var_value(State.latest_results_df)

    @rx.var
    async def results_df_present(self) -> bool:
        """Check if the results dataframe is present."""
        results_df = await self.get_var_value(State.latest_results_df)
        return not results_df.empty

    @rx.event
    def toggle_export_dialog(self):
        """Toggle the export dialog open state."""
        self.export_dialog_open = not self.export_dialog_open

    @rx.event
    async def export_results(self):
        """Export query results as CSV file."""
        try:
            csv_data = (await self.results_df).to_csv(index=False)

            properly_extended_filename = (
                self.export_filename
                if self.export_filename.endswith(".csv")
                else self.export_filename + ".csv"
            )

            return rx.download(data=csv_data, filename=properly_extended_filename)

        except Exception as e:
            print(f"✗ Error exporting: {e}")


export_dialog = rx.dialog.root(
    rx.dialog.content(
        rx.vstack(
            rx.dialog.title(
                "Export Results",
            ),
            rx.dialog.description(
                "Export the query results as a CSV file.",
                size="2",
                color="gray",
            ),
            rx.input(
                placeholder="query_results.csv",
                value=ResultsState.export_filename,
                on_change=ResultsState.set_export_filename,
                size="2",
                width="100%",
            ),
            rx.button(
                rx.icon("download", size=18),
                "Export Results",
                size="3",
                on_click=ResultsState.export_results,
                color_scheme="purple",
                variant="soft",
                cursor="pointer",
            ),
            spacing="4",
            width="100%",
        ),
        rx.flex(
            rx.dialog.close(
                rx.button(
                    "Close",
                    color_scheme="gray",
                    variant="soft",
                    size="2",
                ),
            ),
            spacing="3",
            margin_top="16px",
            justify="end",
        ),
        style={"max_width": "550px"},
    ),
    open=ResultsState.export_dialog_open,
    on_open_change=ResultsState.toggle_export_dialog,
)


# Data table - connected to State.query_results and State.table_columns
def results_section() -> rx.Component:
    return (
        export_dialog,
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.hstack(
                        rx.icon("table", size=20, color="purple"),
                        rx.text(
                            "Query Results",
                            size="4",
                            weight="bold",
                        ),
                        align="center",
                        justify="start",
                    ),
                    rx.cond(
                        ResultsState.results_df_present,
                        rx.button(
                            rx.icon("download", size=18),
                            "Export Results",
                            on_click=ResultsState.toggle_export_dialog,
                            size="3",
                            color_scheme="purple",
                            variant="soft",
                            cursor="pointer",
                        ),
                    ),
                    spacing="2",
                    align="center",
                    justify="between",
                    width="100%",
                ),
                rx.box(
                    rx.cond(
                        ResultsState.results_df_present,
                        rx.cond(
                            ResultsState.results_df_present,
                            rx.data_table(
                                data=ResultsState.results_df,
                                pagination=True,
                                page_size=100,
                                resizable=True,
                                search=False,
                                sort=True,
                                # TODO: make the columns more wide by default
                            ),
                            rx.text(
                                "No results to display",
                                size="2",
                                color="gray",
                                weight="medium",
                            ),
                        ),
                    ),
                    width="100%",
                    height="auto",
                    overflow_x="scroll",
                    overflow_y="auto",
                    position="relative",
                ),
                spacing="3",
            ),
            variant="classic",
            size="3",
            width="100%",
        ),
    )
