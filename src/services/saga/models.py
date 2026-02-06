"""Saga models and types.

This module defines the core models for saga-based distributed transactions:
- StepStatus: Status of a saga step
- StepResult: Result of step execution
- SagaContext: Context passed between steps
- SagaResult: Final result of saga execution
- SagaStep: Protocol for saga steps

Example:
    >>> context = SagaContext(doc_uuid="doc-123")
    >>> result = SagaResult(success=True, doc_uuid="doc-123")
    >>> result.add_executed("postgres_create", step_result)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    pass


class StepStatus(str, Enum):
    """Status of a saga step.

    Attributes:
        PENDING: Step not yet executed
        EXECUTED: Step successfully executed
        COMPENSATED: Step was compensated (rolled back)
        FAILED: Step execution failed
    """

    PENDING = "pending"
    EXECUTED = "executed"
    COMPENSATED = "compensated"
    FAILED = "failed"


@dataclass
class StepResult:
    """Result of a saga step execution.

    Attributes:
        success: Whether the step succeeded
        step_name: Name of the step
        data: Additional data from execution
        error: Error message if failed
    """

    success: bool
    step_name: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class SagaContext:
    """Context passed between saga steps.

    Stores all data needed for step execution and compensation.

    Attributes:
        doc_uuid: Document UUID being processed
        document: Document model (for create/update)
        chunks: List of chunk models
        embeddings: Embedding results
        results: Step execution results for compensation
    """

    doc_uuid: str
    document: Any | None = None
    chunks: list[Any] = field(default_factory=list)
    embeddings: Any | None = None
    results: dict[str, Any] = field(default_factory=dict)

    def set_result(self, step_name: str, data: Any) -> None:
        """Store step result in context.

        Args:
            step_name: Name of the step
            data: Data to store
        """
        self.results[step_name] = data

    def get_result(self, step_name: str) -> Any:
        """Get step result from context.

        Args:
            step_name: Name of the step

        Returns:
            Stored data or None if not found
        """
        return self.results.get(step_name)


@dataclass
class SagaResult:
    """Result of saga execution.

    Tracks all executed steps, compensated steps, and any errors.

    Attributes:
        success: Whether the saga succeeded
        doc_uuid: Document UUID
        executed_steps: List of successfully executed step names
        compensated_steps: List of compensated step names
        error: Error message if failed
        step_results: Detailed results per step
    """

    success: bool
    doc_uuid: str
    executed_steps: list[str] = field(default_factory=list)
    compensated_steps: list[str] = field(default_factory=list)
    error: str | None = None
    step_results: dict[str, StepResult] = field(default_factory=dict)

    def add_executed(self, step_name: str, result: StepResult) -> None:
        """Record executed step.

        Args:
            step_name: Name of the executed step
            result: Step execution result
        """
        self.executed_steps.append(step_name)
        self.step_results[step_name] = result

    def add_compensated(self, step_name: str) -> None:
        """Record compensated step.

        Args:
            step_name: Name of the compensated step
        """
        self.compensated_steps.append(step_name)


class SagaStep(Protocol):
    """Protocol for saga step implementations.

    Each step must implement:
    - name: Identifier for the step
    - execute: Forward execution
    - compensate: Rollback execution
    """

    @property
    def name(self) -> str:
        """Step name for logging and tracking."""
        ...

    async def execute(self, context: SagaContext) -> StepResult:
        """Execute the step.

        Args:
            context: Saga context with data

        Returns:
            StepResult indicating success/failure
        """
        ...

    async def compensate(self, context: SagaContext) -> StepResult:
        """Compensate (rollback) the step.

        Args:
            context: Saga context with data

        Returns:
            StepResult indicating compensation success/failure
        """
        ...
