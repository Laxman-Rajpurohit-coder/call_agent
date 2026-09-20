import os
from pathlib import Path
from typing import Optional
from services.dashboard.app.config import settings

class RecordingStorageService:
    """
    Secure Recording Storage Service.
    Enforces opaque key resolution and directory confinement to prevent
    path traversal vulnerabilities.
    """
    def __init__(self, base_dir: Optional[str] = None):
        if base_dir:
            self.base_dir = os.path.abspath(base_dir)
        else:
            self.base_dir = os.path.abspath(settings.RECORDINGS_DIR)
        os.makedirs(self.base_dir, exist_ok=True)

    def is_safe_path(self, target_path: str) -> bool:
        """Check if target_path is strictly within base_dir."""
        try:
            abs_target = os.path.abspath(target_path)
            # Use commonpath to ensure target is strictly inside base_dir
            return os.path.commonpath([self.base_dir, abs_target]) == self.base_dir
        except Exception:
            return False

    def resolve_recording_path(self, storage_key_or_filename: str) -> Optional[str]:
        """
        Safely resolve a storage key or filename to an absolute path.
        Rejects path traversals with ValueError.
        Returns file path if exists, else None.
        """
        if not storage_key_or_filename:
            return None

        # Clean relative path
        cleaned = storage_key_or_filename.replace("\\", "/").lstrip("/")
        # Check for traversal indicators
        if ".." in cleaned.split("/"):
            raise ValueError("Potential path traversal detected in storage key")

        target_path = os.path.abspath(os.path.join(self.base_dir, cleaned))

        if not self.is_safe_path(target_path):
            raise ValueError("Security violation: Target path escapes recording directory")

        if os.path.exists(target_path) and os.path.isfile(target_path):
            return target_path

        # Secondary fallback: check safe basename in base_dir
        basename = os.path.basename(cleaned)
        fallback_path = os.path.abspath(os.path.join(self.base_dir, basename))
        if self.is_safe_path(fallback_path) and os.path.exists(fallback_path) and os.path.isfile(fallback_path):
            return fallback_path

        return None

    def generate_storage_key(self, organization_id: str, call_id: str, ext: str = "wav") -> str:
        """Generate normalized tenant-scoped storage key."""
        safe_org = "".join(c for c in organization_id if c.isalnum() or c in "-_")
        safe_call = "".join(c for c in call_id if c.isalnum() or c in "-_")
        return f"{safe_org}/{safe_call}.{ext}"

storage_service = RecordingStorageService()
