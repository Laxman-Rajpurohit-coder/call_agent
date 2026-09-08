"""
Stage A (dev machine) implementation. Bounded so the queue itself
becomes the admission-control signal: once it's full, put() raises
QueueFullError instead of silently growing until the box runs out of
memory.
"""

import asyncio
from typing import Any, Optional

from .interface import JobQueue, QueueFullError


class LocalAsyncQueue(JobQueue):
    def __init__(self, maxsize: int = 100):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)

    async def put(self, job: Any) -> None:
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull as exc:
            raise QueueFullError(
                f"queue at capacity ({self._queue.maxsize})"
            ) from exc

    async def get(self, timeout: Optional[float] = None) -> Any:
        if timeout is None:
            return await self._queue.get()
        return await asyncio.wait_for(self._queue.get(), timeout=timeout)

    def qsize(self) -> int:
        return self._queue.qsize()
