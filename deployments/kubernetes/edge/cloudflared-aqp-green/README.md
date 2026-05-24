# cloudflared-aqp-green — Blue/Green Tunnel Lane

Green-lane Cloudflare tunnel connector used for pre-cutover validation.

It reuses the base `cloudflared-aqp` manifest shape but deploys as
`cloudflared-aqp-green` and reads its token from:

- Secret: `cloudflared-aqp-green-token`
- Namespace: `aqp-edge`

## Token bootstrap

PowerShell:

```powershell
$token = cloudflared tunnel token aqp-fund-edge-green
kubectl -n aqp-edge create secret generic cloudflared-aqp-green-token `
  --from-literal=token=$token `
  --dry-run=client -o yaml | kubectl apply -f -
```

Bash:

```bash
token="$(cloudflared tunnel token aqp-fund-edge-green)"
kubectl -n aqp-edge create secret generic cloudflared-aqp-green-token \
  --from-literal=token="$token" \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Deploy

```bash
kubectl apply -k deployments/kubernetes/edge/cloudflared-aqp-green/
kubectl -n aqp-edge rollout status deploy/cloudflared-aqp-green --timeout=180s
```

## Verify

```bash
kubectl -n aqp-edge get deploy,svc -l app=cloudflared-aqp-green
kubectl -n aqp-edge logs deploy/cloudflared-aqp-green --tail=50
```
