"""Shared exception hierarchy for Merit-Trade AI."""
from typing import List, Optional


class MeritBaseException(Exception):
    """Base exception for all Merit-Trade errors."""
    def __init__(self, message: str, code: str = "UNKNOWN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class AuthenticationError(MeritBaseException):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, "AUTH_FAILED")


class AuthorizationError(MeritBaseException):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, "FORBIDDEN")


class InsufficientPlanError(MeritBaseException):
    def __init__(self, required_plan: str):
        super().__init__(
            f"This feature requires the '{required_plan}' plan or higher",
            "PLAN_REQUIRED",
        )
        self.required_plan = required_plan


class RiskEngineRejection(MeritBaseException):
    """Raised when risk engine blocks a trade."""
    def __init__(self, reasons: List[str]):
        self.reasons = reasons
        super().__init__(
            f"Trade rejected by risk engine: {'; '.join(reasons)}",
            "RISK_REJECTED",
        )


class BrokerConnectionError(MeritBaseException):
    def __init__(self, broker: str, detail: str):
        super().__init__(f"Broker connection error ({broker}): {detail}", "BROKER_ERROR")
        self.broker = broker


class SignalGenerationError(MeritBaseException):
    def __init__(self, symbol: str, detail: str):
        super().__init__(f"Signal generation failed for {symbol}: {detail}", "SIGNAL_ERROR")
        self.symbol = symbol


class MarketDataError(MeritBaseException):
    def __init__(self, symbol: str, detail: str):
        super().__init__(f"Market data error for {symbol}: {detail}", "MARKET_DATA_ERROR")


class ModelInferenceError(MeritBaseException):
    def __init__(self, model: str, detail: str):
        super().__init__(f"Model inference failed ({model}): {detail}", "MODEL_ERROR")


class ValidationError(MeritBaseException):
    def __init__(self, field: str, message: str):
        super().__init__(f"Validation error on '{field}': {message}", "VALIDATION_ERROR")
        self.field = field
