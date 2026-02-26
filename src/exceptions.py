"""
Custom exceptions for the P&ID Symbol Library.
"""

from __future__ import annotations


class SymbolError(Exception):
    """Base exception for symbol-related errors."""

    pass


class ClassificationError(SymbolError):
    """Error during symbol classification."""

    pass


class MetadataError(SymbolError):
    """Error during metadata assembly or validation."""

    pass


class PathResolutionError(SymbolError):
    """Error resolving a symbol path."""

    pass


class SVGRenderError(SymbolError):
    """Error rendering SVG to image."""

    pass


class AugmentationError(SymbolError):
    """Error during image augmentation."""

    pass


class ExportError(SymbolError):
    """Error during export operations."""

    pass


class DatabaseError(SymbolError):
    """Database-related errors."""

    pass


class APIError(Exception):
    """Base exception for API errors."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AuthenticationError(APIError):
    """Authentication failure."""

    def __init__(self, message: str = "Invalid API key") -> None:
        super().__init__(message, status_code=401)


class AuthorizationError(APIError):
    """Authorization failure (insufficient permissions)."""

    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(message, status_code=403)


class NotFoundError(APIError):
    """Resource not found."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=404)
