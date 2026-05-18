# Auth0 + FastAPI (2026) Best Practices

As of 2026-05-17, the cleanest pattern for `auth0-fastapi-api>=1.0.0b5` is:

1. instantiate one app-level verifier (`Auth0FastAPI`) with explicit `domain` + `audience`,
2. enforce permissions through route dependencies (`require_auth(scopes=...)`),
3. standardize error handling around the package's `detail.error` contract,
4. align FastAPI infrastructure settings (CORS and reverse-proxy headers) with browser and ingress behavior.

The 1.0 beta line is where DPoP and cache knobs became first-class concerns, so teams should treat this as an API security rollout, not just a package bump.

## 1) Recommended baseline implementation

Use one shared verifier instance and dependency-based auth checks:

```python
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from auth0_fastapi_api import Auth0FastAPI

app = FastAPI()

auth0 = Auth0FastAPI(
    domain="your-tenant.us.auth0.com",
    audience="https://api.your-company.com",
    dpop_enabled=True,
    dpop_required=False,  # start mixed, enforce later
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.your-company.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.get("/api/private")
def private(claims: dict = Depends(auth0.require_auth())):
    return {"sub": claims["sub"]}

@app.post("/api/orders")
def create_order(claims: dict = Depends(auth0.require_auth(scopes=["write:orders"]))):
    return {"ok": True}
```

This aligns with current Auth0 FastAPI SDK guidance and with FastAPI CORS constraints for credentialed browser requests.

## 2) DPoP, scopes, and error response shape

### DPoP rollout model
- `dpop_enabled=True, dpop_required=False`: mixed mode (Bearer and DPoP accepted).
- `dpop_enabled=True, dpop_required=True`: hard DPoP enforcement.
- `dpop_enabled=False`: Bearer-only.

For phased enterprise rollout, mixed mode is typically safest first, then enforce DPoP per client class when telemetry is stable.

### Permission checks
`require_auth(scopes=[...])` is additive/AND-style permission enforcement in practice. Keep API permission names stable (`read:positions`, `write:orders`) and avoid UI-driven string drift.

### Error envelope contract
The practical response shape in the beta docs is:

```json
{
  "detail": {
    "error": "insufficient_scope",
    "error_description": "..."
  }
}
```

Expect these families:
- `400`: malformed/missing auth header, invalid DPoP proof
- `401`: invalid/expired/bad signature/wrong audience token
- `403`: valid token, insufficient scope

Pin exact status semantics in tests, because beta behavior can shift between patch releases.

## 3) Reverse proxy and forwarded headers

Auth works fine behind Nginx/Traefik/ingress, but URL correctness and redirect behavior depend on forwarded headers. FastAPI/Uvicorn should trust only known proxy IPs (`--forwarded-allow-ips`) and parse proxy headers (`--proxy-headers`) in production. Forward at least:
- `X-Forwarded-For`
- `X-Forwarded-Proto`
- `Host` (plus `X-Forwarded-Host` if your stack uses it)

For path-prefix deployments, set `root_path` to match ingress rewriting.

## 4) Breaking-change and migration guidance from 0.x beta

The biggest practical migration step from older 0.x examples is adopting 1.x beta's explicit DPoP and cache tuning surface (`dpop_*`, cache adapter/TTL/entry controls). Public release notes around `1.0.0b5+` are still light on exhaustive migration matrices, so teams should:

1. pin exact versions in CI,
2. run regression tests against auth failures and scope failures,
3. keep an internal compatibility sheet for any status-code or exception changes observed.

## 5) JWKS cache, clock skew, and pytest strategy

### JWKS cache
- Keep one verifier instance per process (do not recreate per request).
- Use bounded cache TTL and eviction controls.
- Handle key rotation by refreshing JWKS when signature validation fails unexpectedly.

### Clock skew
- Keep host clocks synced (NTP).
- Use small leeway for proof/token timing checks where supported.
- Avoid large leeway windows that weaken replay/expiry protection.

### Testing protected routes
Use a two-layer test strategy:

```python
def test_scope_failure(client, bearer_without_scope):
    res = client.post(
        "/api/orders",
        headers={"Authorization": f"Bearer {bearer_without_scope}"},
    )
    assert res.status_code == 403
    body = res.json()
    assert body["detail"]["error"] == "insufficient_scope"
```

- **Unit tests:** dependency override/mocked claims for business logic.
- **Integration tests:** signed JWT + JWKS flow (or deterministic JWKS mock) plus error-shape assertions.
- **Gateway tests:** proxy + CORS + preflight coverage from real browser context.

---

## Sources

- https://pypi.org/project/auth0-fastapi-api/
- https://github.com/auth0/auth0-fastapi-api
- https://auth0.com/docs/quickstart/backend/fastapi
- https://fastapi.tiangolo.com/tutorial/cors/
- https://fastapi.tiangolo.com/advanced/behind-a-proxy/
- https://www.uvicorn.org/settings/
- https://auth0.com/docs/secure/tokens/token-best-practices
- https://auth0.com/docs/secure/tokens/json-web-tokens/locate-json-web-key-sets
