from __future__ import annotations
from typing import Callable, Any
import logging


class ProgressTracker:
    """
    A hierarchical progress tracker that supports weighted sub-tasks and dynamic work totals.
    Designed to feed updates into an async queue via a callback.
    """

    def __init__(
        self,
        name: str = "root",
        weight: float = 1.0,
        parent: ProgressTracker | None = None,
        on_update: Callable[[float], Any] | None = None,
    ):
        """
        Args:
            name: Label for this tracker/phase.
            weight: Relative weight of this tracker within its parent (0.0 to 1.0).
            parent: The parent tracker instance.
            on_update: Callback function (float -> Any) invoked on the ROOT tracker when progress changes.
        """
        self.name = name
        self.weight = weight
        self.parent = parent
        self._on_update = on_update

        # Work tracking
        self.total_work = 0  # 0 means "indeterminate" (0% complete until total is set)
        self.completed_work = 0

        # Children
        self.children: list[ProgressTracker] = []

    def add_phase(self, name: str, weight: float) -> ProgressTracker:
        """Create and register a child phase with a specific weight."""
        child = ProgressTracker(name=name, weight=weight, parent=self)
        self.children.append(child)
        return child

    def set_total(self, total: int):
        """Set the total amount of work units for this tracker."""
        if total < 0:
            raise ValueError("Total work cannot be negative")
        self.total_work = total
        print(
            f"Progress Debug: {self.name} set_total to {total}. Current completed: {self.completed_work}"
        )
        self._notify_root()

    def increment(self, amount: int = 1):
        """Mark work units as completed."""
        self.completed_work += amount
        print(
            f"Progress Debug: {self.name} incremented by {amount}. New total: {self.completed_work}/{self.total_work}"
        )
        self._notify_root()

    def get_progress(self) -> float:
        """
        Calculate the progress of this tracker and all its children.
        Returns a float between 0.0 and 1.0.
        """
        # If this tracker has children, its progress is the weighted sum of children
        if self.children:
            total_weighted_progress = sum(
                child.get_progress() * child.weight for child in self.children
            )
            # Normalize by sum of weights (in case they don't add up to 1.0)
            total_weight = sum(child.weight for child in self.children)
            if total_weight > 0:
                return total_weighted_progress / total_weight
            return 0.0

        # Leaf node: based on completed/total work
        if self.total_work > 0:
            # Clamp to 1.0 max
            return min(self.completed_work / self.total_work, 1.0)

        # Indeterminate state (total_work == 0)
        # If we have completed work but don't know the total yet, we're technically at 0%
        # relative to the unknown goal.
        return 0.0

    def _notify_root(self):
        """Propagate update notification up to the root."""
        if self.parent:
            self.parent._notify_root()
        elif self._on_update:
            # I am root
            current_progress = self.get_progress() * 100
            print(f"Progress Debug: ROOT emitting progress: {current_progress}")
            try:
                self._on_update(current_progress)
            except Exception as e:
                logging.error(f"Error in progress callback: {e}")
