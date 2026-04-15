"""
AI Factory Pipeline v5.8 — App module compatibility shim

Re-exports the FastAPI app from factory.main for backwards compatibility.
Spec Authority: v5.8 §7.4.1
"""

from factory.main import app  # noqa: F401

__all__ = ["app"]
