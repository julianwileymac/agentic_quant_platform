"""End-to-end smoke for the KubernetesAdapter abstraction.

Run inside the api/worker container::

    docker exec aqp-api python -m scripts.kubernetes_smoke

Steps:

1. Print the active adapter selected by
   :func:`aqp.kubernetes.get_kubernetes_adapter` and its
   ``is_available()`` outcome.
2. Print the registered adapter classes (so the operator can verify
   the metaclass picked up every concrete class).
3. Probe each registered adapter's ``is_available()`` independently —
   useful when debugging "why isn't the rpi adapter active?".

Always exits 0; this is a diagnostic tool, not a gating check.
"""
from __future__ import annotations

import sys

from aqp.kubernetes import (
    KubernetesAdapter,
    get_kubernetes_adapter,
    list_adapter_classes,
)


def _print_header(title: str) -> None:
    print()
    print("=" * len(title))
    print(title)
    print("=" * len(title))


def main() -> int:
    _print_header("Active KubernetesAdapter")
    active = get_kubernetes_adapter()
    info = active.describe()
    print(f"  kind:      {info['kind']}")
    print(f"  alias:     {info['alias']}")
    print(f"  available: {info['available']}")

    _print_header("Registered adapter classes")
    classes = list_adapter_classes()
    for alias in sorted(classes):
        cls = classes[alias]
        kind = getattr(cls, "adapter_kind", "?")
        print(f"  {kind:<14} {alias} ({cls.__module__}.{cls.__name__})")

    _print_header("Per-adapter availability probe")
    for alias in sorted(classes):
        cls = classes[alias]
        try:
            instance = cls()
        except Exception as exc:  # noqa: BLE001
            print(f"  {alias}: <construct failed: {exc}>")
            continue
        if not isinstance(instance, KubernetesAdapter):
            continue
        try:
            available = bool(instance.is_available())
        except Exception as exc:  # noqa: BLE001
            print(f"  {alias}: <available probe failed: {exc}>")
            continue
        print(f"  {alias}: available={available}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
