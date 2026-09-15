"""Girly 🌸 — PBKDF2-SHA256 password hashing and session tokens.

Mirrors the original Go auth.go: passwords are hashed with PBKDF2-HMAC-SHA256
(12,000 iterations, 32-byte key) over a salted prefix, so existing
data/girly.json credentials keep verifying unchanged.
"""

import hashlib
import hmac
import re
import secrets

ITERATIONS = 12000
KEY_LENGTH = 32
SALT_PREFIX = "girly:"


def password_policy_error(password: str):
    """User-chosen passwords must combine letters, numbers, and special
    characters. Returns an error message, or None when the password passes."""
    if not re.search(r"[A-Za-z]", password):
        return "password must include at least one letter"
    if not re.search(r"\d", password):
        return "password must include at least one number"
    if not re.search(r"[^A-Za-z0-9]", password):
        return "password must include at least one special character (e.g. ! @ # $)"
    return None


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), (SALT_PREFIX + salt).encode(), ITERATIONS, KEY_LENGTH
    ).hex()


def verify_password(password: str, salt: str, want: str) -> bool:
    got = hash_password(password, salt)
    return hmac.compare_digest(got.encode(), want.encode())


def random_token(n: int = 24) -> str:
    """A hex token built from n random bytes."""
    return secrets.token_hex(n)
