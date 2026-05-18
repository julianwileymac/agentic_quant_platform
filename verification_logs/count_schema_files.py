"""Count exported schema files per format under the verification temp dir."""
from __future__ import annotations

import os
import pathlib
import sys

tmp = pathlib.Path(os.environ.get("TEMP", "/tmp")) / "aqp-schemas-verify"
print(f"root={tmp} exists={tmp.exists()}")
for fmt in ("json", "avro", "pdl"):
    sub = tmp / "schemas" / fmt
    files = sorted(sub.rglob("*"))
    files = [p for p in files if p.is_file()]
    print(f"{fmt}: count={len(files)} dir={sub} exists={sub.exists()}")
    for p in files[:5]:
        print(f"  - {p.relative_to(tmp)}")
    if len(files) > 5:
        print(f"  ... +{len(files) - 5} more")
