import reflex as rx
from ..state import State
from ..components import (
    editor_section,
    gui_section,
    uploader_section,
    # joiner_section,
    results_section,
    execution_tasks_section,
    total_usage_component,
)


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
        width="33%",
        height="100%",
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
        width="33%",
        height="100%",
    )

    # Tabs switch between EDITOR & GUI
    tabs_main_view = rx.tabs.root(
        rx.tabs.list(
            rx.tabs.trigger("SQL Editor", value="EDITOR"),
            rx.tabs.trigger("PDFs -> Table", value="PDFS_TO_TABLE"),
            # TODO: Currently under maintenance
            # rx.tabs.trigger("Smart Join", value="SMART_JOIN"),
        ),
        rx.tabs.content(
            editor_section(),
            value="EDITOR",
        ),
        rx.tabs.content(
            gui_section(),
            value="PDFS_TO_TABLE",
        ),
        # TODO: Currently under maintenance
        # rx.tabs.content(
        #     joiner_section(),
        #     value="SMART_JOIN",
        # ),
        default_value="EDITOR",
        width="100%",
    )

    # Total usage component
    total_usage = total_usage_component()

    # The container with all components
    return rx.box(
        rx.vstack(
            uploader_section(),
            execution_tasks_section(),
            rx.hstack(
                total_usage,
                tables_display,
                pdf_display,
                spacing="6",
                align="start",
                width="100%",
                height="164px",
            ),
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
