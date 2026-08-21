"""Tests for the errors module — error taxonomy and classification."""

from __future__ import annotations

from aura.errors import (
    AuraError,
    ConfigError,
    DatabaseError,
    ErrorCategory,
    ErrorSeverity,
    NetworkError,
    NotFoundError,
    ProviderError,
    RateLimitError,
    RetryDecision,
    StateMachineError,
    TimeoutError,
    ValidationError,
)


class TestErrorTaxonomy:
    def test_config_error_has_correct_category(self) -> None:
        err = ConfigError("Missing config")
        assert err.category == ErrorCategory.CONFIGURATION
        assert err.severity == ErrorSeverity.FATAL
        assert err.retry == RetryDecision.NO_RETRY

    def test_validation_error_no_retry(self) -> None:
        err = ValidationError("Invalid input")
        assert err.retry == RetryDecision.NO_RETRY

    def test_database_error_retry_with_fallback(self) -> None:
        err = DatabaseError("Connection lost")
        assert err.retry == RetryDecision.RETRY_WITH_FALLBACK
        assert err.category == ErrorCategory.DATABASE

    def test_state_machine_error_includes_violations(self) -> None:
        err = StateMachineError("Invalid transition", violations=["F001: OPEN -> VERIFIED"])
        assert err.detail is not None
        assert "F001" in err.detail

    def test_network_error_retry(self) -> None:
        err = NetworkError("DNS timeout")
        assert err.retry == RetryDecision.RETRY

    def test_timeout_error_retry_with_fallback(self) -> None:
        err = TimeoutError("Request timed out")
        assert err.retry == RetryDecision.RETRY_WITH_FALLBACK

    def test_rate_limit_error_includes_retry_after(self) -> None:
        err = RateLimitError("Too many requests", retry_after=30)
        assert "30" in err.detail

    def test_provider_error_includes_provider_name(self) -> None:
        err = ProviderError("Auth failed", provider="test-provider")
        assert "test-provider" in str(err)

    def test_not_found_error(self) -> None:
        err = NotFoundError("Cycle 5 not found")
        assert err.category == ErrorCategory.NOT_FOUND

    def test_error_to_dict(self) -> None:
        err = ConfigError("Bad config", detail="Invalid JSON")
        d = err.to_dict()
        assert d["category"] == "configuration"
        assert d["severity"] == "fatal"
        assert d["retry"] == "no_retry"
        assert d["detail"] == "Invalid JSON"

    def test_base_error_can_chain_original(self) -> None:
        original = ValueError("original error")
        err = AuraError("Wrapped error", category=ErrorCategory.INTERNAL, original=original)
        assert err.original is original
