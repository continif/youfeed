"""Test smoke per il modulo password hashing."""

from __future__ import annotations

from app.utils.passwords import hash_password, needs_rehash, verify_password


def test_hash_and_verify_round_trip() -> None:
    plain = "MySuperPassword2026!"
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_hash_is_not_plaintext() -> None:
    plain = "anotherSecret123"
    hashed = hash_password(plain)
    assert hashed != plain
    assert hashed.startswith("$argon2")


def test_needs_rehash_false_for_current_params() -> None:
    plain = "fresh-password-2026"
    hashed = hash_password(plain)
    assert needs_rehash(hashed) is False
