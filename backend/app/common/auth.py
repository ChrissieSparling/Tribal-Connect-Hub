"""Authentication helpers for hashing and verifying passwords.

The functions in this module provide a minimal, dependency-free approach
for securely handling user passwords.  Passwords are hashed using
``hashlib.pbkdf2_hmac`` with a per-password salt and verified in
constant time using :func:`hmac.compare_digest`.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re

_PBKDF_ITERATIONS = 100_000

# Regex enforcing 8+ chars with upper, lower, digit and special character
_PASSWORD_RE = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$"
)

def validate_password(password: str) -> bool:
    """Return ``True`` if ``password`` meets basic complexity rules."""
    # return bool(_PASSWORD_RE.match(password))
    """Validate password complexity.
    The default policy requires a minimum length of eight characters and at
    least one alphabetic character and one digit.
    """
    if len(password) < 8:
        return False
    has_alpha = any(ch.isalpha() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    return has_alpha and has_digit

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


# __all__ = ["validate_password", "hash_password", "safe_verify_password"]