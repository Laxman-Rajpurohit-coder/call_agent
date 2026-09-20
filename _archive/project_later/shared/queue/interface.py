"""
Queue abstraction. Call gateway and workers depend only on this
interface — never directly on asyncio.Queue or Redis. That means the
move from "one machine" to "multiple machines" is a matter of swapping
the implementation passed in at startup, not rewriting the app.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class JobQueue(ABC):
    """Minimal contract every queue backend must satisfy."""

    @abstractmethod
    async def put(self, job: Any) -> None:
        """Enqueue a job."""

    @abstractmethod
    async def get(self, timeout: Optional[float] = None) -> Any:
        """Dequeue a job, waiting up to `timeout` seconds. Raises
        asyncio.TimeoutError if nothing arrives in time — callers use
        this to implement per-job timeouts (Phase 4: admission control),
        not to hang forever."""

    @abstractmethod
    def qsize(self) -> int:
        """Current depth — used for admission control and metrics."""


class QueueFullError(Exception):
    """Raised when a bounded queue is at capacity. The gateway should
    catch this and reject/redirect the call (CALL_REJECTED_AT_CAPACITY)
    rather than let the job block indefinitely."""
