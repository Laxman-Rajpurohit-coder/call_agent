import os
import time
from typing import Dict

class CircuitBreaker:
    """
    3-State Circuit Breaker (CLOSED, OPEN, HALF_OPEN) tracking local provider health.
    - CLOSED: Local provider is healthy. Local calls proceed.
    - OPEN: Local provider failed > failure_threshold times. Cloud fallback is BLOCKED to protect cloud bill.
    - HALF_OPEN: Cooldown expired. Allows ONE probe attempt. If successful, transitions to CLOSED.
    """
    def __init__(self, name: str, failure_threshold: int = 5, cooldown_seconds: float = 60.0):
        self.name = name
        self.failure_threshold = int(os.environ.get("CIRCUIT_BREAKER_FAILURE_THRESHOLD", failure_threshold))
        self.cooldown_seconds = float(os.environ.get("CIRCUIT_BREAKER_COOLDOWN_SECONDS", cooldown_seconds))
        
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.failure_count = 0
        self.last_failure_time = 0.0

    def can_fallback(self) -> bool:
        now = time.time()
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            if now - self.last_failure_time >= self.cooldown_seconds:
                print(f"[CircuitBreaker '{self.name}'] Cooldown expired. Transitioning from OPEN ➔ HALF_OPEN.")
                self.state = "HALF_OPEN"
                return True
            return False
        elif self.state == "HALF_OPEN":
            return True
        return False

    def record_success(self):
        if self.state != "CLOSED":
            print(f"[CircuitBreaker '{self.name}'] Local call succeeded! Transitioning to CLOSED.")
        self.state = "CLOSED"
        self.failure_count = 0

    def record_failure(self, is_qualifying: bool = True):
        if not is_qualifying:
            return

        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == "HALF_OPEN":
            print(f"[CircuitBreaker '{self.name}'] Probe failed in HALF_OPEN. Transitioning back to OPEN.")
            self.state = "OPEN"
        elif self.failure_count >= self.failure_threshold:
            print(f"[CircuitBreaker '{self.name}'] Failure threshold reached ({self.failure_count}/{self.failure_threshold}). Opening circuit!")
            self.state = "OPEN"
