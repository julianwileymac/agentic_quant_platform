# build/docker/aqp_control_plane

Standalone container for the `aqp_control_plane/` micro-project. Two-stage build:

| Stage     | Base                | Purpose                                                                |
| --------- | ------------------- | ---------------------------------------------------------------------- |
| `builder` | `python:3.11-slim`  | Install `aqp_platform_core` + `aqp_control_plane` editable             |
| `runtime` | `python:3.11-slim`  | Strip dev deps; copy site-packages; expose port 9000; non-root user    |

**Strict isolation invariant** — the build context excludes `aqp/` (the AQP monolith). The image must run with `aqp_platform_core` as its only AQP-side dependency. A CI lint enforces this:

```bash
rg --type python "^from aqp(\.|$)|^import aqp(\.|$)" aqp_control_plane/ && exit 1
```

See [ADR 005 — separated control plane](../../../docs/architecture/decisions/005-separated-control-plane.md).

## Build

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --file build/docker/aqp_control_plane/Dockerfile \
  --tag ghcr.io/julianwiley/aqp-control-plane:dev \
  .
```

## Local run (standalone)

The control plane must function without `aqp_client`:

```bash
docker run --rm -it \
  -p 9000:9000 \
  -e AQP_CP_PROVIDER=docker_compose \
  -e AUTH0_AUDIENCE=https://api.aqp.internal/manage \
  -e AUTH0_ISSUER=https://my-tenant.us.auth0.com/ \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  ghcr.io/julianwiley/aqp-control-plane:dev
```

Then `curl http://localhost:9000/manage/health` should return 200.
