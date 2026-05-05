"""Argon2id hashing per password.

Configurazione: parametri OWASP 2023 per Argon2id (m=19MB, t=2, p=1).
Adeguati a un VPS modesto, target ~50ms/hash.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Parametri rivedibili in produzione misurando il tempo reale.
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=19 * 1024,  # 19 MiB
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:  # noqa: BLE001
        return False
    return True


def needs_rehash(hashed: str) -> bool:
    """True se la stringa hashata usa parametri obsoleti rispetto a quelli attuali."""
    return _hasher.check_needs_rehash(hashed)
