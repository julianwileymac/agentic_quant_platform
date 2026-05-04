# AQP Market Data Superset Bundle

This directory holds a curated, version-controlled Superset asset bundle for
the `AQP Market Data Explorer` dashboard. The layout matches what
`superset export-dashboards` (and AQP's `aqp viz export`) produces:

```
aqp_market_data/
├── metadata.yaml
├── databases/<slug>.yaml
├── datasets/<schema>/<table>.yaml
├── charts/<slug>.yaml
└── dashboards/aqp-market-data-explorer.yaml
```

## How to populate

1. Bring up the visualization profile:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.viz.yml --profile visualization up -d
   ```

2. Sync the curated assets into Superset (creates the database, datasets,
   charts, and dashboard from `aqp.visualization.superset_assets`):

   ```bash
   curl -X POST http://localhost:8000/visualizations/superset/sync
   ```

3. Hand-tune the dashboard layout in the Superset UI as desired
   (filters, RBAC, embedding settings, refresh frequency, etc).

4. Export the dashboard back into this directory:

   ```bash
   aqp viz export --out deploy/superset/bundles/aqp_market_data \
     --slug aqp-market-data-explorer
   ```

   The exporter writes a zip first, then unzips it into the target dir.

5. Commit the YAML files. Subsequent imports replay the curated state:

   ```bash
   aqp viz import deploy/superset/bundles/aqp_market_data
   ```

## Notes

- Database `sqlalchemy_uri` values are stripped of secrets on export and
  must be re-supplied via `aqp viz import --password <slug>=<password>`
  if they use a non-trivial password. The default `trino://trino@trino:8080/iceberg`
  needs no password.
- The bundle is designed to round-trip: any `aqp viz export` followed by
  `aqp viz import` should leave Superset semantically unchanged.
- The `metadata.yaml` checked in below is a placeholder so the directory
  exists in version control before the first export.
