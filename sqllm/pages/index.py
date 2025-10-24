import reflex as rx
from reflex_monaco import monaco
from ..state import State
from ..components.gui import gui_section


@rx.page(route="/", title="SQLLM")
def index() -> rx.Component:
    csv_upload_section = rx.vstack(
        rx.upload(
            rx.vstack(
                rx.icon("file-up", size=32, color="teal"),
                rx.button(
                    rx.icon("folder-open", size=16),
                    "Select CSV Files",
                    color_scheme="teal",
                    size="2",
                    variant="soft",
                ),
                rx.text(
                    "Drag and drop CSV files here or click to browse",
                    size="2",
                    color="gray",
                    align="center",
                ),
                align="center",
                spacing="3",
            ),
            id="csv_upload",
            multiple=True,
            accept={"text/csv": [".csv"]},
            max_files=5,
            border="2px dashed",
            border_color="teal",
            padding="2em",
            border_radius="12px",
            background="var(--teal-a2)",
            width="100%",
        ),
        rx.cond(
            rx.selected_files("csv_upload").length() > 0,
            rx.vstack(
                rx.text("Selected files:", weight="bold", size="2"),
                rx.vstack(
                    rx.foreach(
                        rx.selected_files("csv_upload"),
                        lambda file: rx.hstack(
                            rx.icon("file-text", size=16, color="teal"),
                            rx.text(file, size="2"),
                            spacing="2",
                            align="center",
                        ),
                    ),
                    spacing="2",
                    width="100%",
                ),
                spacing="2",
                width="100%",
                padding="1em",
                background="var(--gray-a2)",
                border_radius="8px",
            ),
        ),
        rx.button(
            rx.icon("upload", size=18),
            "Upload CSV Files",
            on_click=State.handle_csv_upload(rx.upload_files(upload_id="csv_upload")),
            size="3",
            color_scheme="teal",
            width="100%",
            cursor="pointer",
        ),
        spacing="4",
        width="100%",
    )

    pdf_upload_section = rx.vstack(
        rx.upload(
            rx.vstack(
                rx.icon("file-plus", size=32, color="purple"),
                rx.button(
                    rx.icon("folder-open", size=16),
                    "Select PDF Files",
                    color_scheme="purple",
                    size="2",
                    variant="soft",
                ),
                rx.text(
                    "Drag and drop PDF files here or click to browse",
                    size="2",
                    color="gray",
                    align="center",
                ),
                align="center",
                spacing="3",
            ),
            id="pdf_upload",
            multiple=True,
            accept={"application/pdf": [".pdf"]},
            max_files=5,
            border="2px dashed",
            border_color="purple",
            padding="2em",
            border_radius="12px",
            background="var(--purple-a2)",
            width="100%",
        ),
        rx.cond(
            rx.selected_files("pdf_upload").length() > 0,
            rx.vstack(
                rx.text("Selected files:", weight="bold", size="2"),
                rx.vstack(
                    rx.foreach(
                        rx.selected_files("pdf_upload"),
                        lambda file: rx.hstack(
                            rx.icon("file", size=16, color="purple"),
                            rx.text(file, size="2"),
                            spacing="2",
                            align="center",
                        ),
                    ),
                    spacing="2",
                    width="100%",
                ),
                spacing="2",
                width="100%",
                padding="1em",
                background="var(--gray-a2)",
                border_radius="8px",
            ),
        ),
        rx.button(
            rx.icon("upload", size=18),
            "Upload PDF Files",
            on_click=State.handle_pdf_upload(rx.upload_files(upload_id="pdf_upload")),
            size="3",
            color_scheme="purple",
            width="100%",
            cursor="pointer",
        ),
        spacing="4",
        width="100%",
    )

    upload_dialog = rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.dialog.title(
                    rx.cond(
                        State.upload_dialog_mode == "csv",
                        rx.hstack(
                            rx.icon("database", size=24, color="teal"),
                            "Import CSV Files",
                            spacing="2",
                            align="center",
                        ),
                        rx.hstack(
                            rx.icon("file-plus", size=24, color="purple"),
                            "Store PDF Files",
                            spacing="2",
                            align="center",
                        ),
                    )
                ),
                rx.dialog.description(
                    rx.cond(
                        State.upload_dialog_mode == "csv",
                        "Upload CSV files to query them with SQL. Each file becomes a DuckDB table.",
                        "Upload PDFs to store them on disk. Reference the saved path in llm_pdf_to_table().",
                    ),
                    size="2",
                    color="gray",
                ),
                rx.cond(
                    State.upload_dialog_mode == "csv",
                    csv_upload_section,
                    pdf_upload_section,
                ),
                spacing="4",
                width="100%",
            ),
            rx.flex(
                rx.dialog.close(
                    rx.button(
                        "Close",
                        on_click=State.close_upload_dialog,
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
        open=State.upload_dialog_open,
        on_open_change=State.toggle_upload_dialog_open,
    )

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
    )

    # Monaco SQL Editor - bound to State.sql_query
    editor_section = rx.card(
        rx.vstack(
            rx.hstack(
                rx.hstack(
                    rx.icon("code", size=20, color="indigo"),
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
                    on_click=State.execute_query,
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
                    value=State.sql_query,
                    on_change=State.set_sql_query,
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

    # Tabs switch between EDITOR & GUI
    tabs_main_view = rx.tabs.root(
        rx.tabs.list(
            rx.tabs.trigger("SQL Editor", value="EDITOR"),
            rx.tabs.trigger("Batch Task Manager", value="GUI"),
        ),
        rx.tabs.content(
            editor_section,
            value="EDITOR",
        ),
        rx.tabs.content(
            gui_section(),
            value="GUI",
        ),
        default_value="EDITOR",
        width="100%",
    )

    # Success message display
    success_display = rx.cond(
        State.success_message != "",
        rx.callout(
            State.success_message,
            icon="check",
            color_scheme="green",
            role="status",
            size="2",
        ),
    )

    # Error message display (only shows when there's an error)
    error_display = rx.cond(
        State.error_message != "",
        rx.callout(
            State.error_message,
            icon="triangle_alert",
            color_scheme="red",
            role="alert",
            size="2",
        ),
    )

    # Export dialog
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
                    value=State.export_filename,
                    on_change=State.set_export_filename,
                    size="2",
                    width="100%",
                ),
                rx.button(
                    rx.icon("download", size=18),
                    "Export Results",
                    on_click=State.export_results,
                    size="3",
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
                        on_click=State.close_export_dialog,
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
        open=State.export_dialog_open,
        on_open_change=State.toggle_export_dialog_open,
    )

    # Data table - connected to State.query_results and State.table_columns
    results_section = (
        rx.card(
            rx.cond(
                State.is_loading,
                rx.hstack(
                    rx.spinner(),
                    rx.text("Loading..."),
                    spacing="2",
                    width="100%",
                    align="center",
                    justify="center",
                ),
                rx.vstack(
                    rx.hstack(
                        rx.icon("table", size=20, color="purple"),
                        rx.text(
                            "Query Results",
                            size="4",
                            weight="bold",
                        ),
                        rx.spacer(),
                        rx.cond(
                            State.result_count != "",
                            rx.badge(
                                State.result_count,
                                color_scheme="purple",
                                variant="soft",
                                size="2",
                            ),
                            rx.text(""),
                        ),
                        rx.button(
                            rx.icon("download", size=18),
                            "Export Results",
                            on_click=State.open_export_dialog,
                            size="3",
                            color_scheme="purple",
                            variant="soft",
                            cursor="pointer",
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    rx.data_table(
                        data=State.query_results_df,
                        pagination=True,
                        search=False,
                        sort=True,
                        style={"height": "600px", "width": "100%"},
                    ),
                    spacing="3",
                ),
            ),
            variant="classic",
            size="3",
            width="100%",
        ),
    )

    # Header with title and import button
    header = rx.box(
        upload_dialog,
        rx.hstack(
            rx.hstack(
                rx.icon("database", size=32, color="teal"),
                rx.vstack(
                    rx.heading(
                        "SQL Query Tool for CSV Files",
                        size="7",
                        weight="bold",
                        color="teal",
                    ),
                    rx.text(
                        "Upload CSV files and query them using SQL powered by DuckDB",
                        size="3",
                        color="gray",
                    ),
                    align="start",
                    spacing="1",
                ),
                spacing="3",
                align="center",
            ),
            rx.spacer(),
            rx.hstack(
                rx.button(
                    rx.icon("upload", size=18),
                    "Import CSV",
                    color_scheme="teal",
                    size="3",
                    variant="solid",
                    cursor="pointer",
                    on_click=State.open_upload_dialog_csv,
                ),
                rx.button(
                    rx.icon("file-plus", size=18),
                    "Store PDF",
                    color_scheme="purple",
                    size="3",
                    variant="soft",
                    cursor="pointer",
                    on_click=State.open_upload_dialog_pdf,
                ),
                spacing="2",
            ),
            width="100%",
            align="center",
        ),
        padding="2em",
        background="linear-gradient(135deg, var(--teal-a2) 0%, var(--indigo-a2) 100%)",
        border_radius="16px",
        margin_bottom="1em",
        width="100%",
    )

    # The container with all components
    return rx.box(
        rx.vstack(
            header,
            rx.hstack(
                tables_display,
                pdf_display,
                spacing="6",
                align="start",
                width="100%",
            ),
            tabs_main_view,
            success_display,
            error_display,
            export_dialog,
            results_section,
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
