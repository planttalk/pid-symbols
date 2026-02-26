"""Studio module for the P&ID symbol editor.

Provides:
- symbols: Symbol management (list, load, save, stats)
- augmentation: Augmentation preview and generation
- reports: Unrealistic reports handling
- server: HTTP server for the browser-based editor
"""

from . import augmentation
from . import export_completed
from . import reports
from . import server
from . import symbols

__all__ = [
    "symbols",
    "augmentation",
    "reports",
    "server",
    "export_completed",
]
