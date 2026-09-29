from __future__ import annotations


class AppError(Exception):
    """Stable application error that can be mapped to an HTTP response."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        retryable: bool = False,
    ) -> None:
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable
        super().__init__(code)
