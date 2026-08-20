"""
auth.py
Password hashing (PBKDF2, stdlib only) and JWT session tokens for
StudyForge's optional login. No account is required to use the app —
this only powers the "sync my history across devices" flow.
"""

import binascii
import hashlib
import hmac
import os
import time

import jwt

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-insecure-secret-change-me-in-.env")
JWT_ALGORITHM = "HS256"
TOKEN_LIFETIME_SECONDS = 60 * 60 * 24 * 30  # 30 days

PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{binascii.hexlify(salt).decode()}${binascii.hexlify(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$")
        salt = binascii.unhexlify(salt_hex)
        expected = binascii.unhexlify(digest_hex)
    except (ValueError, binascii.Error):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(actual, expected)


def create_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": int(time.time()) + TOKEN_LIFETIME_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None