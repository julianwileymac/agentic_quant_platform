# aqp_ui Dockerfile

Multi-stage Next.js 14+ App Router build emitting a slim `node:20-alpine`
production image (~120 MB compressed) for both `linux/amd64` and
`linux/arm64`.

## Build

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --file aqp_platform/build/docker/aqp_ui/Dockerfile \
  --tag ghcr.io/julianwiley/aqp-ui:dev \
  --push \
  .
```

## Runtime env

Secrets are NEVER baked into the image. The Kubernetes Deployment uses
`envFrom: secretRef: aqp-ui-secrets` synced by External Secrets Operator
from HashiCorp Vault. See
`aqp_platform/deployments/kubernetes/base/aqp-ui/external-secret.yaml`.

Build-time args (`AQP_UI_BASE_URL`, `AQP_CLAIMS_NAMESPACE`,
`NEXT_PUBLIC_AQP_UI_VERSION`) are non-sensitive and may be embedded in
the image.

## CVE-2025-29927

Next.js MUST be pinned `>=14.2.25` (or `>=15.2.3` if we move to 15.x)
to mitigate the middleware bypass vulnerability. The pin lives in
`aqp_ui/package.json`. Even with the pin, the rule remains: NEVER rely
solely on `middleware.ts` for auth — every route handler under
`src/app/api/*` re-checks `getSession()` server-side.

## Health

`GET /api/healthz` returns `{ status: "ok", ts, version }`. It does NOT
contact upstream services so the marketing site stays available even
when the AQP backend is down. A deeper probe lives at
`/api/healthz/deep` (sprint 7).
