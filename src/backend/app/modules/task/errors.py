class LostTaskLease(RuntimeError):
    """Raised when a worker no longer owns a task."""
