import reflex as rx
from sqllm.state import State


def execution_tasks_section() -> rx.Component:
    """UI Card for ExecutionTasks, wrapped in a top-level card with fixed height and full width."""
    return rx.card(
        rx.vstack(
            rx.heading("Query Execution Tasks", size="4", weight="medium"),
            rx.cond(
                State.execution_tasks,
                rx.hstack(
                    rx.foreach(
                        State.execution_tasks,
                        lambda task: rx.card(
                            rx.vstack(
                                rx.badge(
                                    task.type,
                                    color_scheme="purple",
                                    variant="soft",
                                    mr="2",
                                ),
                                rx.markdown(task.summary, size="2"),
                                rx.cond(
                                    task.result,
                                    # Show Results button if result is present
                                    rx.button(
                                        rx.icon("table"),
                                        "Show Results",
                                        size="2",
                                        color_scheme="purple",
                                        variant="soft",
                                        on_click=State.show_specific_results(task.id),
                                        disabled=False,
                                        width="100%",
                                    ),
                                    # Otherwise show the progress bar
                                    rx.progress(
                                        value=task.percent_done,
                                        show_value=True,
                                        width="100%",
                                    ),
                                ),
                                rx.cond(
                                    task.error,
                                    rx.callout(
                                        f"Error: {task.error}",
                                        icon="circle_alert",
                                        color_scheme="red",
                                    ),
                                ),
                                spacing="0",
                                align_items="start",
                                width="100%",
                            ),
                            max_width="50%",
                            min_width="20%",
                            variant="surface",
                            box_shadow="sm",
                        ),
                    ),
                    align_items="stretch",
                    width="100%",
                    height="100%",
                    overflow_x="scroll",
                ),
                rx.text("No execution tasks yet.", italic=True, color="gray"),
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
        overflow_y="none",
        p="4",
        variant="classic",
    )
