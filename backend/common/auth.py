"""Compatibility wrapper for authentication helpers.

This module re-exports the real implementations located under
``app.common.auth`` so existing imports continue to work.
"""
from __future__ import annotations

from app.common.auth import hash_password, safe_verify_password, validate_password

__all__ = ["hash_password", "safe_verify_password", "validate_password"]