# Control-plane topology

Phase 0 of the AQP infra-expansion plan. The single source of truth
for "what services exist, where do they live, what URLs do they
expose" is [`aqp_platform/configs/deployment/topology.yaml`](../configs/deployment/topology.yaml).
Both the AQP monolith (`aqp/`) and the standalone control plane
(`aqp_control_plane/`) read from the same YAML through the shared
loader at
[`aqp_platform_core.topology.load_topology`](../aqp_platform_core/src/aqp_platform_core/topology/loader.py).

## Resolution order

1. Hardcoded default in `Settings`.
2. `AQP_*` environment variable.
3. `aqp_platform/configs/deployment/topology.yaml` fallback (this layer).

The Phase 0 fallback ONLY fires when an `AQP_*` env var is unset
(checked via `Settings.model_fields_set`). Operators who explicitly
override an env var keep their override.

## URL fallback table

The mapping lives in
[`aqp/config/topology_fallback.py::URL_FALLBACK_FIELDS`](../aqp/config/topology_fallback.py).
Each row says: when topology declares `endpoints[<endpoint_name>]`
on the service whose id is `<service_id>`, use that URL as the
fallback for the matching `Settings` field. Adding a new service =
new row in the table + new `services:` entry in `topology.yaml`.

## Control-plane routes

`aqp_control_plane` exposes the topology over HTTP:

| Route | Purpose |
|---|---|
| `GET /manage/topology` | Full snapshot (services + targets). |
| `GET /manage/topology/services` | Filterable service list (?role=, ?cluster=). |
| `GET /manage/topology/services/{id}` | Single descriptor (matched by id or alias). |
| `GET /manage/topology/services/{id}/endpoint?name=` | Resolve a named URL. |
| `GET /manage/topology/services/{id}/health` | Live provider probe. |
| `GET /manage/topology/targets` | List deployment targets. |
| `POST /manage/topology/reload` | Drop the cache and reload from disk (admin:cluster). |

The frontend at [/admin/topology](../aqp_client/src/routes/admin/topology/page.tsx)
renders the topology grouped by role with a "Probe health" button
per service.

## Adding a new shared service

1. Append a `services:` entry to
   [`aqp_platform/configs/deployment/topology.yaml`](../configs/deployment/topology.yaml)
   with `cluster`, `namespace`, `protocols`, and `endpoints`
   populated.
2. Add the new `Settings` field in
   [`aqp/config/settings.py`](../aqp/config/settings.py) (default
   `""`).
3. Add a row to `URL_FALLBACK_FIELDS` mapping the new `Settings`
   field to the topology endpoint name.
4. Add the namespace to `targets.<env>.services` so the topology
   round-trips for that environment.
5. (Optional) Add a `/cache/<category>` populator on the
   [`MetadataPrefetcher`](../aqp/cache/prefetch.py) so the
   `<EntityPicker kind="<category>" />` in the frontend has dropdown
   data.
