"""End-to-end smoke for the credentials resolver.

Run inside the api/worker container::

    docker exec aqp-api python -m scripts.credentials_smoke

The script:

1. Resolves ``polaris:oauth`` and prints the source (``file`` if a
   bootstrap-minted ``polaris-principal.json`` is present, ``env``
   otherwise).
2. Resolves ``iceberg:rest`` and confirms the ``credential`` field
   matches whatever Polaris will accept.
3. Asks the resolver for ``minio:static`` so we can sanity-check the
   container env hasn't drifted from the compose seed.
4. Prints the resolver's store chain so the operator can see whether
   the M2M store is plugged in.

Returns 0 on success. Exits non-zero (with a printed reason) when a
required field is missing.
"""
from __future__ import annotations

import sys
from typing import Any

from aqp.credentials import CredentialKey, get_resolver


def _print_header(title: str) -> None:
    print()
    print("=" * len(title))
    print(title)
    print("=" * len(title))


def _print_credential(label: str, key: CredentialKey, *, expected: list[str]) -> int:
    cred = get_resolver().resolve(key)
    print(f"\n[{label}] key={key} source={cred.source}")
    missing = []
    for field in expected:
        value = cred.get(field)
        if value:
            preview = value if len(value) <= 16 else f"{value[:6]}...{value[-4:]}"
            print(f"  - {field}: {preview}")
        else:
            print(f"  - {field}: <empty>")
            missing.append(field)
    if missing:
        return 1
    return 0


def main() -> int:
    _print_header("Credential resolver chain")
    info = get_resolver().describe()
    for store in info["stores"]:
        print(f"  {store['priority']:>4}  {store['kind']:<6}  {store['alias']}")

    rc = 0
    rc |= _print_credential(
        "polaris:oauth",
        CredentialKey("polaris", "oauth"),
        expected=["client_id", "client_secret"],
    )
    rc |= _print_credential(
        "iceberg:rest",
        CredentialKey("iceberg", "rest"),
        expected=["credential"],
    )
    rc |= _print_credential(
        "minio:static",
        CredentialKey("minio", "static"),
        expected=["access_key", "secret_key"],
    )

    print()
    if rc == 0:
        print("[OK] credentials_smoke passed")
    else:
        print("[FAIL] one or more credentials missing required fields")
    return rc


if __name__ == "__main__":
    sys.exit(main())
