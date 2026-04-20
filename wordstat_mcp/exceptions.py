class WordstatError(RuntimeError):
    """Generic Wordstat API error."""


class WordstatConfigError(WordstatError):
    """Configuration error."""


class RetriableError(WordstatError):
    """Transient error that can be retried."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after
