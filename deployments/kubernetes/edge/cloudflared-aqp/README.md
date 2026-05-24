# cloudflared-aqp — AQP.FUND Cloudflare Tunnel

Outbound-only Cloudflare Tunnel connector for the AQP platform domain.
This is owned by `agentic_quant_platform` and runs in the `aqp-edge`
namespace. It is independent of the `julianwiley-portal` tunnel
(`rpi_kubernetes/kubernetes/base-services/cloudflared/`, namespace
`edge`), so changes to AQP cannot disrupt the personal portal and vice
versa.

## Public hostnames

The Cloudflare-managed tunnel `aqp-fund-edge`
(`0cd12089-38ee-4dfb-95ba-65d2daa7b88b`) routes:

| Hostname | In-cluster service |
| --- | --- |
| `aqp.fund` | `http://aqp-client.aqp.svc.cluster.local:80` |
| `api.aqp.fund` | `http://aqp-core.aqp.svc.cluster.local:8000` |
| `manage.aqp.fund` | `http://aqp-cp.aqp-admin.svc.cluster.local:80` |

DNS records are proxied CNAMEs to:

`0cd12089-38ee-4dfb-95ba-65d2daa7b88b.cfargotunnel.com`

## One-time setup

The tunnel token is resolved through `CredentialResolver` (AGENTS rule 26).
The local k8s Secret is created out-of-band so the kustomization never
commits or overwrites a live token.

PowerShell:

```powershell
$token = cloudflared tunnel token aqp-fund-edge
kubectl -n aqp-edge create secret generic cloudflared-aqp-token `
  --from-literal=token=$token `
  --dry-run=client -o yaml | kubectl apply -f -
```

Bash:

```bash
token="$(cloudflared tunnel token aqp-fund-edge)"
kubectl -n aqp-edge create secret generic cloudflared-aqp-token \
  --from-literal=token="$token" \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Deploy

Apply only this connector:

```powershell
kubectl apply -k deployments/kubernetes/edge/cloudflared-aqp/
kubectl -n aqp-edge rollout status deploy/cloudflared-aqp --timeout=180s
```

Or apply through the AQP base kustomization:

```powershell
kubectl apply -k deployments/kubernetes/base/
```

## Verify

```powershell
kubectl -n aqp-edge get deploy,pods,svc -l app=cloudflared-aqp
kubectl -n aqp-edge logs -l app=cloudflared-aqp --tail=50
```

Healthy logs include:

```text
Registered tunnel connection ...
Updated to new configuration config_version=...
```

Public checks:

```powershell
curl https://aqp.fund
curl https://api.aqp.fund/livez
curl https://manage.aqp.fund/manage/livez
```

## Migration

Lifted from `rpi_kubernetes/kubernetes/base-services/cloudflared-aqp/`
during the final decoupling of AQP from `rpi_kubernetes`. The original
manifests in rpi_kubernetes are deleted in the same change so there is
exactly one canonical owner.
