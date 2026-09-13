# -----------------------------------------------------------------------------
# Role: Exports the Python block package API.
# File Name: __init__.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2024-04-08
# -----------------------------------------------------------------------------

from .block import PythonBlock, PythonBlockError

__all__ = ["PythonBlock", "PythonBlockError"]
