"""Compare the OpenMetadata models discovered by SchemaExporter against the
files actually written to the verification temp dir.
"""
from __future__ import annotations

import os
import pathlib

from aqp.metadata.schema_export import SchemaExporter

tmp = pathlib.Path(os.environ.get("TEMP", "/tmp")) / "aqp-schemas-verify"
exporter = SchemaExporter()
models = exporter.discover_models()
model_names = sorted(m.__name__ for m in models)
print(f"discovered_models={len(model_names)}")
for name in model_names:
    print(f"  model: {name}")

for fmt, ext in (("json", ".schema.json"), ("avro", ".avsc"), ("pdl", ".pdl")):
    sub = tmp / "schemas" / fmt
    found = sorted(
        p.name.replace(ext, "") for p in sub.glob(f"*{ext}") if p.is_file()
    )
    print(f"\n{fmt}: files={len(found)}")
    for n in found:
        print(f"  file: {n}")
    missing = sorted(set(model_names) - set(found))
    extra = sorted(set(found) - set(model_names))
    print(f"missing_in_{fmt}={missing}")
    print(f"extra_in_{fmt}={extra}")
