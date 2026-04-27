"""Quick end-to-end smoke for the Director against a real corpus.

Used as a sanity check before kicking off the full regulatory ingest.
Run inside the api/worker container::

    docker exec aqp-api python -m scripts._director_smoke --path /host-downloads/cfpb --namespace aqp_cfpb
"""
from __future__ import annotations

import argparse
import time

from aqp.data.pipelines import discover_datasets, plan_ingestion


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True)
    parser.add_argument("--namespace", default="aqp")
    args = parser.parse_args()

    print(f"[smoke] discovering {args.path} ...")
    t0 = time.time()
    ds = discover_datasets(args.path)
    families = [x for x in ds if x.family != "__assets__"]
    print(f"[smoke] discovery: {len(families)} families in {time.time() - t0:.1f}s")
    for f in families[:20]:
        members = len(f.members)
        mb = round(f.total_bytes / (1024 * 1024), 1)
        print(f"   - {f.family}: {members} member(s), {mb} MB")

    print(f"[smoke] calling Director (LLM) ...")
    t0 = time.time()
    plan = plan_ingestion(
        ds,
        source_path=args.path,
        namespace=args.namespace,
        allowed_namespaces=[args.namespace],
    )
    elapsed = time.time() - t0
    print(
        f"[smoke] director: {elapsed:.1f}s, used={plan.director_used}, "
        f"error={plan.director_error}"
    )
    print(f"[smoke] tables planned: {len(plan.datasets)}")
    for p in plan.datasets[:20]:
        print(
            f"   - {p.family} -> {p.iceberg_identifier} "
            f"(floor={p.expected_min_rows}, domain={p.domain_hint})"
        )
    if plan.director_raw:
        print("[smoke] director_raw[:500]:")
        print(plan.director_raw[:500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
