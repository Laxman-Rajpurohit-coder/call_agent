from typing import Dict, Any

class RetryService:
    RETRYABLE_STATUSES = {"NO_ANSWER", "BUSY", "TEMPORARY_ERROR", "TIMEOUT"}
    NON_RETRYABLE_STATUSES = {"COMPLETED", "INTERESTED", "NOT_INTERESTED", "OPTED_OUT", "INVALID_NUMBER", "HUMAN_HANDOFF"}

    def should_retry(self, status: str, outcome: str, current_attempts: int, max_retries: int) -> bool:
        if current_attempts >= max_retries:
            return False
        if outcome in self.NON_RETRYABLE_STATUSES:
            return False
        if status in self.RETRYABLE_STATUSES or status == "failed":
            return True
        return False

retry_service = RetryService()
