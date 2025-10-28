import reflex as rx
from ..state import State


class UploaderState(rx.State):
    """State management for the file uploader."""

    files: list[rx.UploadFile] = []
    is_uploading: bool = False
    upload_dialog_open: bool = False

    @rx.event
    async def handle_upload(self, files: list[rx.UploadFile]):
        """Upload files using the appropriate handlers for each type."""
        self.is_uploading = True
        yield

        # separate csv and pdf files
        csv_files: list[rx.UploadFile] = []
        pdf_files: list[rx.UploadFile] = []
        for file in files:
            if file.content_type == "text/csv":
                csv_files.append(file)
            elif file.content_type == "application/pdf":
                pdf_files.append(file)

        # upload csv and pdf files using appropriate handlers
        state = await self.get_state(State)
        if len(csv_files) > 0:
            await state.handle_csv_upload(csv_files)
        if len(pdf_files) > 0:
            await state.handle_pdf_upload(pdf_files)

        self.is_uploading = False
        self.upload_dialog_open = False

    @rx.event
    def close_upload_dialog(self):
        """Close the upload dialog."""
        self.upload_dialog_open = False

    @rx.event
    def toggle_upload_dialog_open(self, value: bool):
        """Toggle the upload dialog open state."""
        self.upload_dialog_open = value

    @rx.event
    def open_upload_dialog(self):
        """Open the upload dialog."""
        self.upload_dialog_open = True


def uploader_section() -> rx.Component:
    upload_section = rx.vstack(
        rx.upload(
            rx.vstack(
                rx.icon("file-up", size=32, color="teal"),
                rx.button(
                    rx.icon("folder-open", size=16),
                    "Select CSV or PDF Files",
                    color_scheme="teal",
                    size="2",
                    variant="soft",
                ),
                rx.text(
                    "Drag and drop CSV or PDF files here or click to browse",
                    size="2",
                    color="gray",
                    align="center",
                ),
                align="center",
                spacing="3",
            ),
            id="csv_pdf_upload",
            multiple=True,
            accept={"text/csv": [".csv"], "application/pdf": [".pdf"]},
            max_files=5,
            border="2px dashed",
            border_color="teal",
            padding="2em",
            border_radius="12px",
            background="var(--teal-a2)",
            width="100%",
        ),
        rx.cond(
            rx.selected_files("csv_pdf_upload").length() > 0,
            rx.vstack(
                rx.text("Selected files:", weight="bold", size="2"),
                rx.vstack(
                    rx.foreach(
                        rx.selected_files("csv_pdf_upload"),
                        lambda file: rx.hstack(
                            rx.icon(
                                "file-text",
                                size=16,
                                color="teal",
                            ),
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
            rx.cond(
                UploaderState.is_uploading,
                rx.spinner(),
                "Upload Files",
            ),
            on_click=UploaderState.handle_upload(rx.upload_files(upload_id="csv_pdf_upload")),
            size="3",
            color_scheme="teal",
            width="100%",
            cursor="pointer",
            disabled=UploaderState.is_uploading | ~rx.selected_files("csv_pdf_upload") > 0,
        ),
        spacing="4",
        width="100%",
    )

    upload_dialog = rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.dialog.title(
                    rx.hstack(
                        rx.icon("database", size=24, color="teal"),
                        "Upload CSV or PDF Files",
                        spacing="2",
                        align="center",
                    )
                ),
                rx.dialog.description(
                    "Upload CSV files to query with SQL (each file becomes a DuckDB table). "
                    "Upload PDFs to store them on disk; reference saved paths in llm_pdf_to_table().",
                    size="2",
                    color="gray",
                ),
                upload_section,
                spacing="4",
                width="100%",
            ),
            rx.flex(
                rx.dialog.close(
                    rx.button(
                        "Close",
                        on_click=UploaderState.close_upload_dialog,
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
        open=UploaderState.upload_dialog_open,
        on_open_change=UploaderState.toggle_upload_dialog_open,
    )

    return rx.box(
        upload_dialog,
        rx.hstack(
            rx.hstack(
                rx.icon("database", size=32, color="teal"),
                rx.vstack(
                    rx.heading(
                        "SQL Query Tool for CSV & PDF Files",
                        size="7",
                        weight="bold",
                        color="teal",
                    ),
                    rx.text(
                        "Upload CSV files to query them using SQL, or store PDFs for later use",
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
                    "Upload CSV or PDF",
                    color_scheme="teal",
                    size="3",
                    variant="solid",
                    cursor="pointer",
                    on_click=UploaderState.open_upload_dialog,
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
