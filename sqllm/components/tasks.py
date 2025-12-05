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
                                rx.vstack(
                                    rx.badge(
                                        task.type,
                                        color_scheme="purple",
                                        variant="soft",
                                        mr="2",
                                    ),
                                    rx.hstack(
                                        rx.cond(
                                            task.usage,
                                            rx.badge(
                                                f"${task.usage.cost:.6f}",
                                                variant="solid",
                                                size="1",
                                            ),
                                            None,
                                        ),
                                        # Cancel button: Only show if task is NOT done (no result/error)
                                        # and percentage < 100
                                        rx.cond(
                                            task.percent_done < 100,
                                            rx.icon_button(
                                                rx.icon("x"),
                                                size="1",
                                                color_scheme="red",
                                                variant="soft",
                                                on_click=State.cancel_execution_task(
                                                    task
                                                ),
                                            ),
                                            None,
                                        ),
                                        align="center",
                                        spacing="2",
                                    ),
                                    width="100%",
                                    justify="between",
                                    align="start",
                                ),
                                rx.markdown(task.summary, size="2"),
                                rx.cond(
                                    task.result,
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
                            variant="surface",
                        ),
                    ),
                    align="center",
                ),
                rx.text("No execution tasks yet.", italic=True, color="gray"),
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
        variant="classic",
    )
