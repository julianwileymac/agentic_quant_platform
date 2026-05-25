---
title: 'AQP.FUND Blue/Green Cutover'
summary: '- Overlay: `aqp_platform/deployments/kubernetes/overlays/tower-green/` - Tunnel lane: `aqp_platform/deployments/kubernetes/edge/cloudflared-aqp-green/` - Verification: `scripts/verify_blue_green_cutov...'
owner: sre-team
last_reviewed: 2026-05-25
audience: both
---

# AQP.FUND Blue/Green Cutover

Runbook for migrating `aqp.fund` traffic to the tower cluster with a short,
controlled DNS/tunnel switch and immediate rollback path.

## Green lane artifacts

- Overlay: `aqp_platform/deployments/kubernetes/overlays/tower-green/`
- Tunnel lane: `aqp_platform/deployments/kubernetes/edge/cloudflared-aqp-green/`
- Verification: `scripts/verify_blue_green_cutover.sh`

Green hostnames:

- `aqp-green.aqp.fund`
- `api-green.aqp.fund`
- `manage-green.aqp.fund`

## 1) Pre-cutover prep

1. Ensure `tower-dev` is healthy:

   ```bash
   bash scripts/verify_tower_cluster.sh
   ```

2. Update Auth0 app allow-lists so both blue and green URLs are valid during transition.
   Use `aqp_platform/terraform/modules/auth0_identity` inputs:
   - `callback_urls` + `cutover_callback_urls`
   - `logout_urls` + `cutover_logout_urls`
   - `web_origins` + `cutover_web_origins`

3. Create green tunnel token secret:

   ```bash
   token="$(cloudflared tunnel token aqp-fund-edge-green)"
   kubectl -n aqp-edge create secret generic cloudflared-aqp-green-token \
     --from-literal=token="$token" \
     --dry-run=client -o yaml | kubectl apply -f -
   ```

## 2) Deploy green lane

```bash
kubectl apply -k aqp_platform/deployments/kubernetes/edge/cloudflared-aqp-green/
kubectl apply -k aqp_platform/deployments/kubernetes/overlays/tower-green/
```

## 3) Validate before switch

```bash
bash scripts/verify_blue_green_cutover.sh
CHECK_EXTERNAL=true bash scripts/verify_blue_green_cutover.sh
```

## 4) Cut over traffic

Perform the controlled switch in Cloudflare:

- point DNS/app routing to green hostnames (or update tunnel ingress mapping)
- confirm health endpoints:
  - `https://aqp-green.aqp.fund`
  - `https://api-green.aqp.fund/livez`
  - `https://manage-green.aqp.fund/manage/livez`

Once stable, update canonical host routing (`aqp.fund`, `api.aqp.fund`,
`manage.aqp.fund`) to the tower green lane.

## 5) Rollback

Immediate rollback commands:

```bash
kubectl apply -k aqp_platform/deployments/kubernetes/overlays/tower-dev/
kubectl delete -k aqp_platform/deployments/kubernetes/edge/cloudflared-aqp-green/
```

Then restore blue DNS/tunnel routing and rerun baseline checks.
