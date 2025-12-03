import reflex as rx
import pandas as pd
import logging
from .backend.Engine.engine import Engine, TableRepresentationObject
from .backend.LLM.OpenAI import OpenAIProvider
from .backend.LLM.Azure import AzureProvider
from rxconfig import isProd
from .backend.LLM.base import TokenUsage, LLMProvider
from .models.execution_task import ExecutionTask
import duckdb

# TODO: these need to exist on session level
llm: LLMProvider = AzureProvider() if isProd() else OpenAIProvider()
engine: Engine = Engine(conn=duckdb.connect(":memory:"), llm=llm)


class State(rx.State):
    """
    Top level state management for SQLLM application.
    """

    execution_tasks: list[ExecutionTask] = []
    displayed_results_df: pd.DataFrame = pd.DataFrame()
    available_tables: list[TableRepresentationObject] = []
    available_pdfs: list[str] = []
    total_token_usage: TokenUsage = TokenUsage()

    @rx.event(background=True)
    async def submit_execution_task(self, task: ExecutionTask):
        """
        Submit an execution task to be run in the background.

        Args:
            task (ExecutionTask): The execution task to submit.
        """
        async with self:
            self.execution_tasks.insert(0, task)
        yield

        try:
            async for progress, is_done, result, usage in engine.execute(task.sql):
                async with self:
                    task.percent_done = progress

                    if is_done and result is not None:
                        task.result = result
                        task.warnings = result.warnings
                        task.usage = usage

                    self.execution_tasks = self.execution_tasks.copy()
                yield

        except Exception as e:
            async with self:
                task.error = e
                task.percent_done = 100
                self.execution_tasks = self.execution_tasks.copy()
            logging.error(f"Task execution failed: {task.error}")
            yield

        async with self:
            if task.result is not None:
                self.displayed_results_df = task.result.df
                self.available_tables = engine.list_tables()

    @rx.event
    def update_available_tables(self):
        """Update the available tables."""
        self.available_tables = engine.list_tables()

    @rx.event
    def add_available_pdf(self, file_path: str):
        """Add a new available PDF."""
        if file_path not in self.available_pdfs:
            self.available_pdfs.append(file_path)

    @rx.event
    def show_specific_results(self, task_id: str):
        """Show the results of a specific execution task."""
        print(f"exec task ids: {[task.id for task in self.execution_tasks]}")
        for task in self.execution_tasks:
            if str(task.id) == task_id:
                print(f"showing results for task {task.id}")
                print(f"task result df: {task.result.df}")
                self.displayed_results_df = task.result.df
                break
