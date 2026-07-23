class MarketDataError(RuntimeError):
    """Base error for market-data workflows."""


class InputValidationError(MarketDataError):
    """Raised when a user request is invalid."""


class DataFetchError(MarketDataError):
    """Raised when an upstream market-data provider fails."""


class DataQualityError(MarketDataError):
    """Raised when returned market data fails quality checks."""


class StorageError(MarketDataError):
    """Raised when a data artifact cannot be persisted."""


class StrategyError(RuntimeError):
    """Base error for strategy-management workflows."""


class StrategyValidationError(StrategyError):
    """Raised when a strategy definition is invalid."""


class StrategyNameConflictError(StrategyError):
    """Raised when a normalized strategy name already exists."""


class StrategyNotFoundError(StrategyError):
    """Raised when a strategy cannot be found."""


class StrategyReadOnlyError(StrategyError):
    """Raised when a built-in strategy is modified or deleted."""


class StrategyStorageError(StrategyError):
    """Raised when a strategy artifact cannot be persisted."""

class BacktestError(RuntimeError):
    """Base error for backtest workflows."""


class BacktestValidationError(BacktestError):
    """Raised when backtest inputs or strategy rules are invalid."""


class BacktestExecutionError(BacktestError):
    """Raised when a backtest cannot be completed."""
