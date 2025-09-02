"""Common authentication helpers used across the project.

This module provides minimal password hashing and verification utilities
without relying on external dependencies.  Passwords are hashed using
``hashlib.pbkdf2_hmac`` and compared using ``hmac.compare_digest`` to avoid
leaking timing information.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Tuple

_PBKDF_ITERATIONS = 100_000


def hash_password(password: str, *, salt: bytes | str | None = None) -> str:
    """Return a salted PBKDF2 hash for ``password``.

    The result is formatted as ``"<salt>$<hash>"`` where both components are
    hex encoded.  Supplying an explicit ``salt`` allows reproducible hashes for
    tests; otherwise a cryptographically secure random salt is generated.
    """
    if salt is None:
        salt_bytes = os.urandom(16)
    elif isinstance(salt, str):
        salt_bytes = bytes.fromhex(salt)
    else:
        salt_bytes = salt
    pwd_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_bytes, _PBKDF_ITERATIONS
    )
    return f"{salt_bytes.hex()}${pwd_hash.hex()}"


def safe_verify_password(password: str, stored: str) -> bool:
    """Return ``True`` if ``password`` matches ``stored`` hash.

    ``stored`` must be a string in the format produced by :func:`hash_password`.
    The comparison uses :func:`hmac.compare_digest` for constant-time safety.
    """
    try:
        salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    new_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF_ITERATIONS
    )
    return hmac.compare_digest(new_hash.hex(), hash_hex)