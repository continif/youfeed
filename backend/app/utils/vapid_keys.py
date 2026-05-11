"""CLI per generare le chiavi VAPID (Phase 1.2.E).

Genera una coppia di chiavi compatibili Web Push e stampa i valori da
inserire in `.env`:

    python -m app.utils.vapid_keys

Output:
    VAPID_PRIVATE_KEY=...
    VAPID_PUBLIC_KEY=...

Le due chiavi NON cambiano dopo essere state generate: regenerarle
invalida tutte le subscription esistenti. Fare backup.
"""

from __future__ import annotations

import base64
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid01


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def main() -> None:
    # Genero la chiave privata EC P-256 (ECDSA / VAPID standard) e la
    # serializzo nei formati che py_vapid e i browser si aspettano:
    # - private = PEM (o raw 32-byte big-endian b64url; PEM è più portabile)
    # - public  = uncompressed point (65 byte) → b64url, usato sia per
    #             `VAPID_PUBLIC_KEY` sia esposto come `applicationServerKey`
    #             al PushManager.subscribe() del browser.
    private_key = ec.generate_private_key(ec.SECP256R1())

    # PEM private
    pem_priv = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")

    # Public uncompressed point (65 byte: 0x04 || x || y)
    public_numbers = private_key.public_key().public_numbers()
    pub_bytes = (
        b"\x04"
        + public_numbers.x.to_bytes(32, "big")
        + public_numbers.y.to_bytes(32, "big")
    )
    pub_b64 = _b64url(pub_bytes)

    # Validate via Vapid01 round-trip
    v = Vapid01.from_pem(pem_priv.encode("ascii"))
    assert v.public_key is not None

    # Output: usiamo PEM per la private (multi-line) → \n-escape per .env
    pem_priv_one_line = pem_priv.strip().replace("\n", "\\n")

    print(
        "Aggiungi al tuo .env (NON commettere in git):\n",
        file=sys.stderr,
    )
    print(f'VAPID_PRIVATE_KEY="{pem_priv_one_line}"')
    print(f"VAPID_PUBLIC_KEY={pub_b64}")
    print(
        "\nVAPID_SUBJECT è già nel default settings (mailto:noreply@youfeed.it),\n"
        "modificalo se vuoi un altro contact point.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
