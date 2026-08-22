"""AURA error taxonomy — typed, classified, actionable errors.

Every error in the system must be classified so it can be:
- Properly logged
- Correctly retried (or not)
- Accurately reported to users
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCategory(StrEnum):
    """Top-level error classification."""

    CONFIGURATION = "configuration"
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    NETWORK = "network"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    PROVIDER = "provider"
    DEPENDENCY = "dependency"
    DATABASE = "database"
    PARSING = "parsing"
    INTERNAL = "internal"
    NOT_FOUND = "not_found"
    STATE_MACHINE = "state_machine"


class ErrorSeverity(StrEnum):
    """How severe the error is."""

    FATAL = "fatal"       # Cannot continue
    ERROR = "error"       # Operation failed
    WARNING = "warning"   # Non-blocking issue
    INFO = "info"         # Informational


class RetryDecision(StrEnum):
    """Whether an operation should be retried."""

    RETRY = "retry"             # Transient failure, retry with backoff
    NO_RETRY = "no_retry"       # Permanent failure, do not retry
    RETRY_WITH_FALLBACK = "retry_with_fallback"  # Retry, then fall back


class AuraError(Exception):
    """Base exception for all AURA errors."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.INTERNAL,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        retry: RetryDecision = RetryDecision.NO_RETRY,
        detail: str | None = None,
        original: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.severity = severity
        self.retry = retry
        self.detail = detail
        self.original = original

    def to_dict(self) -> dict:
        return {
            "message": str(self),
            "category": self.category.value,
            "severity": self.severity.value,
            "retry": self.retry.value,
            "detail": self.detail,
        }


# ── Specific error types ────────────────────────────────────────────────────


class ConfigError(AuraError):
    """Configuration is invalid or missing."""

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(
            message,
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.FATAL,
            retry=RetryDecision.NO_RETRY,
            detail=detail,
        )


class ValidationError(AuraError):
    """Input validation failed."""

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(
            message,
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.ERROR,
            retry=RetryDecision.NO_RETRY,
            detail=detail,
        )


class DatabaseError(AuraError):
    """Database operation failed."""

    def __init__(
        self,
        message: str,
        retry: RetryDecision = RetryDecision.RETRY_WITH_FALLBACK,
        detail: str | None = None,
    ) -> None:
        super().__init__(
            message,
            category=ErrorCategory.DATABASE,
            severity=ErrorSeverity.ERROR,
            retry=retry,
            detail=detail,
        )


class StateMachineError(AuraError):
    """State machine violation detected."""

    def __init__(self, message: str, violations: list[str] | None = None) -> None:
        super().__init__(
            message,
            category=ErrorCategory.STATE_MACHINE,
            severity=ErrorSeverity.ERROR,
            retry=RetryDecision.NO_RETRY,
            detail="\n".join(violations) if violations else None,
        )


class NotFoundError(AuraError):
    """Resource not found."""

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(
            message,
            category=ErrorCategory.NOT_FOUND,
            severity=ErrorSeverity.ERROR,
            retry=RetryDecision.NO_RETRY,
            detail=detail,
        )


class NetworkError(AuraError):
    """Network operation failed."""

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(
            message,
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.ERROR,
            retry=RetryDecision.RETRY,
            detail=detail,
        )


class TimeoutError(AuraError):
    """Operation timed out."""

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(
            message,
            category=ErrorCategory.TIMEOUT,
            severity=ErrorSeverity.ERROR,
            retry=RetryDecision.RETRY_WITH_FALLBACK,
            detail=detail,
        )


class RateLimitError(AuraError):
    """Rate limit exceeded."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(
            message,
            category=ErrorCategory.RATE_LIMIT,
            severity=ErrorSeverity.WARNING,
            retry=RetryDecision.RETRY,
            detail=f"Retry after {retry_after}s" if retry_after else None,
        )


class ProviderError(AuraError):
    """External provider returned an error."""

    def __init__(self, message: str, provider: str, detail: str | None = None) -> None:
        super().__init__(
            f"[{provider}] {message}",
            category=ErrorCategory.PROVIDER,
            severity=ErrorSeverity.ERROR,
            retry=RetryDecision.RETRY_WITH_FALLBACK,
            detail=detail,
        )
