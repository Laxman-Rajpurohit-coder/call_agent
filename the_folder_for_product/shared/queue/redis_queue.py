"""
Stage B (multi-box) implementation — NOT implemented yet on purpose.
This file exists so the seam is visible in the codebase from day one,
per the plan: don't build Redis until load-testing on LocalAsyncQueue
actually shows we need to go multi-box.

When that day comes: implement RedisQueue against the same JobQueue
interface (e.g. via a Redis list + BLPOP for get(), LPUSH for put(),
LLEN for qsize()), and the call gateway / workers need zero changes —
only the startup wiring that picks which queue implementation to use.
"""

from .interface import JobQueue


class RedisQueue(JobQueue):
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "RedisQueue is a placeholder for Stage B. Implement once "
            "load testing on LocalAsyncQueue justifies going multi-box."
        )
