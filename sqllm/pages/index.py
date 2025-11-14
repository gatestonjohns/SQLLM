import reflex as rx
from ..state import State
from ..components import editor_section, gui_section, uploader_section, joiner_section, results_section, execution_tasks_section


@rx.page(route="/", title="SQLLM")
def index() -> rx.Component:
    # Available tables display
    tables_display = rx.card(
        rx.cond(
            State.available_tables.length() > 0,
            rx.vstack(
                rx.hstack(
                    rx.icon("table", size=20, color="blue"),
                    rx.text(
                        "Available Tables",
                        size="3",
                        weight="bold",
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.hstack(
                    rx.foreach(
                        State.available_tables,
                        lambda table: rx.popover.root(
                            rx.popover.trigger(
                                rx.badge(
                                    rx.icon("table-2", size=14),
                                    table.name,
                                    color_scheme="blue",
                                    variant="soft",
                                    size="2",
                                )
                            ),
                            rx.popover.content(
                                rx.vstack(
                                    rx.text(
                                        f"Rows: {table.row_count}",
                                        size="2",
                                        weight="medium",
                                    ),
                                    rx.table.root(
                                        rx.table.header(
                                            rx.table.row(
                                                rx.table.column_header_cell("Column"),
                                                rx.table.column_header_cell("Type"),
                                            )
                                        ),
                                        rx.table.body(
                                            rx.foreach(
                                                table.columns,
                                                lambda col: rx.table.row(
                                                    rx.table.cell(col.name),
                                                    rx.table.cell(col.type),
                                                ),
                                            )
                                        ),
                                        size="1",
                                    ),
                                    spacing="2",
                                    align="start",
                                ),
                                side="top",
                                align="start",
                                style={"min_width": "240px"},
                            ),
                        ),
                    ),
                    spacing="2",
                    align="center",
                    wrap="wrap",
                ),
                spacing="3",
                align="start",
                max_height="100px",
                overflow_y="auto",
            ),
            rx.hstack(
                rx.icon("info", size=20, color="gray"),
                rx.text(
                    "No tables loaded yet. Click 'Import CSV' to get started.",
                    size="2",
                    color="gray",
                ),
                spacing="2",
                align="center",
            ),
        ),
        variant="surface",
        size="2",
        width="50%",
    )

    pdf_display = rx.card(
        rx.cond(
            State.available_pdfs.length() > 0,
            rx.vstack(
                rx.hstack(
                    rx.icon("file", size=20, color="purple"),
                    rx.text(
                        "Stored PDFs",
                        size="3",
                        weight="bold",
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.vstack(
                    rx.foreach(
                        State.available_pdfs,
                        lambda pdf: rx.code(pdf, size="2"),
                    ),
                    spacing="1",
                    align="start",
                    width="100%",
                    max_height="100px",
                    overflow_y="auto",
                ),
                spacing="3",
                align="start",
            ),
            rx.hstack(
                rx.icon("info", size=20, color="gray"),
                rx.text(
                    "Upload PDFs to reference their saved paths in llm_pdf_to_table().",
                    size="2",
                    color="gray",
                ),
                spacing="2",
                align="center",
            ),
        ),
        variant="surface",
        size="2",
        width="50%",
    )

    # # Session usage and cost tracking card
    # usage_stats_card = rx.card(
    #     rx.vstack(
    #         rx.hstack(
    #             rx.icon("activity", size=20, color="green"),
    #             rx.text("Session Usage & Cost", size="3", weight="bold"),
    #             spacing="2",
    #             align="center",
    #         ),
    #         rx.cond(
    #             State.query_count > 0,
    #             rx.hstack(
    #                 # Left side - Cumulative stats
    #                 rx.hstack(
    #                     rx.vstack(
    #                         rx.text(
    #                             "Session Total", size="2", weight="bold", color="green"
    #                         ),
    #                         spacing="1",
    #                     ),
    #                     rx.vstack(
    #                         rx.text(
    #                             "Total Tokens", size="1", color="gray", weight="medium"
    #                         ),
    #                         rx.badge(
    #                             f"{State.cumulative_total_tokens:,}",
    #                             color_scheme="green",
    #                             variant="soft",
    #                             size="2",
    #                         ),
    #                         spacing="1",
    #                         align="center",
    #                     ),
    #                     rx.vstack(
    #                         rx.text("Input", size="1", color="gray", weight="medium"),
    #                         rx.badge(
    #                             f"{State.cumulative_input_tokens:,}",
    #                             color_scheme="blue",
    #                             variant="soft",
    #                             size="2",
    #                         ),
    #                         spacing="1",
    #                         align="center",
    #                     ),
    #                     rx.vstack(
    #                         rx.text("Output", size="1", color="gray", weight="medium"),
    #                         rx.badge(
    #                             f"{State.cumulative_output_tokens:,}",
    #                             color_scheme="blue",
    #                             variant="soft",
    #                             size="2",
    #                         ),
    #                         spacing="1",
    #                         align="center",
    #                     ),
    #                     rx.vstack(
    #                         rx.text(
    #                             "Total Cost", size="1", color="gray", weight="medium"
    #                         ),
    #                         rx.badge(
    #                             f"${State.cumulative_cost:.4f}",
    #                             color_scheme="green",
    #                             variant="soft",
    #                             size="2",
    #                         ),
    #                         spacing="1",
    #                         align="center",
    #                     ),
    #                     rx.vstack(
    #                         rx.text("Queries", size="1", color="gray", weight="medium"),
    #                         rx.badge(
    #                             f"{State.query_count}",
    #                             color_scheme="purple",
    #                             variant="soft",
    #                             size="2",
    #                         ),
    #                         spacing="1",
    #                         align="center",
    #                     ),
    #                     spacing="3",
    #                     align="center",
    #                     flex="1",
    #                 ),
    #                 # Divider
    #                 rx.divider(orientation="vertical", size="4"),
    #                 # Right side - Last query stats
    #                 rx.hstack(
    #                     rx.vstack(
    #                         rx.text(
    #                             "Last Query", size="2", weight="bold", color="orange"
    #                         ),
    #                         spacing="1",
    #                     ),
    #                     rx.vstack(
    #                         rx.text(
    #                             "Total Tokens", size="1", color="gray", weight="medium"
    #                         ),
    #                         rx.badge(
    #                             f"{State.current_query_total_tokens:,}",
    #                             color_scheme="orange",
    #                             variant="soft",
    #                             size="2",
    #                         ),
    #                         spacing="1",
    #                         align="center",
    #                     ),
    #                     rx.vstack(
    #                         rx.text("Input", size="1", color="gray", weight="medium"),
    #                         rx.badge(
    #                             f"{State.current_query_input_tokens:,}",
    #                             color_scheme="blue",
    #                             variant="soft",
    #                             size="2",
    #                         ),
    #                         spacing="1",
    #                         align="center",
    #                     ),
    #                     rx.vstack(
    #                         rx.text("Output", size="1", color="gray", weight="medium"),
    #                         rx.badge(
    #                             f"{State.current_query_output_tokens:,}",
    #                             color_scheme="blue",
    #                             variant="soft",
    #                             size="2",
    #                         ),
    #                         spacing="1",
    #                         align="center",
    #                     ),
    #                     rx.vstack(
    #                         rx.text(
    #                             "Query Cost", size="1", color="gray", weight="medium"
    #                         ),
    #                         rx.badge(
    #                             f"${State.current_query_cost:.4f}",
    #                             color_scheme="orange",
    #                             variant="soft",
    #                             size="2",
    #                         ),
    #                         spacing="1",
    #                         align="center",
    #                     ),
    #                     spacing="3",
    #                     align="center",
    #                     flex="1",
    #                 ),
    #                 spacing="4",
    #                 align="start",
    #                 width="100%",
    #             ),
    #             rx.hstack(
    #                 rx.icon("info", size=16, color="gray"),
    #                 rx.text(
    #                     "No queries executed yet. Run a query to see usage statistics.",
    #                     size="2",
    #                     color="gray",
    #                 ),
    #                 spacing="2",
    #                 align="center",
    #             ),
    #         ),
    #         spacing="3",
    #         align="start",
    #     ),
    #     variant="surface",
    #     size="2",
    #     width="100%",
    # )

    # Tabs switch between EDITOR & GUI
    tabs_main_view = rx.tabs.root(
        rx.tabs.list(
            rx.tabs.trigger("SQL Editor", value="EDITOR"),
            rx.tabs.trigger("PDFs -> Table", value="PDFS_TO_TABLE"),
            rx.tabs.trigger("Smart Join", value="SMART_JOIN"),
        ),
        rx.tabs.content(
            editor_section(),
            value="EDITOR",
        ),
        rx.tabs.content(
            gui_section(),
            value="PDFS_TO_TABLE",
        ),
        rx.tabs.content(
            joiner_section(),
            value="SMART_JOIN",
        ),
        default_value="SMART_JOIN",  # TODO: what do we want as default tab?
        width="100%",
    )

    # # Success message display
    # success_display = rx.cond(
    #     State.success_message != "",
    #     rx.callout(
    #         State.success_message,
    #         icon="check",
    #         color_scheme="green",
    #         role="status",
    #         size="2",
    #     ),
    # )

    # # Error message display (only shows when there's an error)
    # error_display = rx.cond(
    #     State.error_message != "",
    #     rx.callout(
    #         State.error_message,
    #         icon="triangle_alert",
    #         color_scheme="red",
    #         role="alert",
    #         size="2",
    #     ),
    # )

    # # Export dialog
    # export_dialog = rx.dialog.root(
    #     rx.dialog.content(
    #         rx.vstack(
    #             rx.dialog.title(
    #                 "Export Results",
    #             ),
    #             rx.dialog.description(
    #                 "Export the query results as a CSV file.",
    #                 size="2",
    #                 color="gray",
    #             ),
    #             rx.input(
    #                 placeholder="query_results.csv",
    #                 value=State.export_filename,
    #                 on_change=State.set_export_filename,
    #                 size="2",
    #                 width="100%",
    #             ),
    #             rx.button(
    #                 rx.icon("download", size=18),
    #                 "Export Results",
    #                 on_click=State.export_results,
    #                 size="3",
    #                 color_scheme="purple",
    #                 variant="soft",
    #                 cursor="pointer",
    #             ),
    #             spacing="4",
    #             width="100%",
    #         ),
    #         rx.flex(
    #             rx.dialog.close(
    #                 rx.button(
    #                     "Close",
    #                     on_click=State.close_export_dialog,
    #                     color_scheme="gray",
    #                     variant="soft",
    #                     size="2",
    #                 ),
    #             ),
    #             spacing="3",
    #             margin_top="16px",
    #             justify="end",
    #         ),
    #         style={"max_width": "550px"},
    #     ),
    #     open=State.export_dialog_open,
    #     on_open_change=State.toggle_export_dialog_open,
    # )

    # The container with all components
    return rx.box(
        rx.vstack(
            uploader_section(),
            execution_tasks_section(),
            rx.hstack(
                tables_display,
                pdf_display,
                spacing="6",
                align="start",
                width="100%",
            ),
            # usage_stats_card,
            tabs_main_view,
            # success_display,
            # error_display,
            # export_dialog,
            results_section(),
            spacing="5",
            width="100%",
        ),
        padding="2em",
        max_width="1400px",
        margin="0 auto",
        width="100%",
    )


app = rx.App()
app.add_page(index)
