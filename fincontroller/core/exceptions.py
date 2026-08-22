"""
Domain-specific exceptions for FinController.
"""


class FinControllerException(Exception):
    """Base exception for FinController."""
    pass


class IngestionError(FinControllerException):
    """Raised when data ingestion or parsing fails."""
    pass


class ReconciliationError(FinControllerException):
    """Raised when a reconciliation step encounters fatal corruption."""
    pass


class AuditIntegrityError(FinControllerException):
    """Raised when the cryptographic audit chain verification fails due to tampering."""
    pass


class CircuitBreakerOpenException(FinControllerException):
    """Raised when an upstream call is prevented because the circuit breaker is open."""
    pass


class RAGProcessingError(FinControllerException):
    """Raised when the vector store or LLM pipeline fails."""
    pass
