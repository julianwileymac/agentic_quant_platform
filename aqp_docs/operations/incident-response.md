# Operations runbook — Incident response

Standard playbook for diagnosing + recovering from AQP production incidents.

## Triage tree

```
                         Incident detected
                                |
              +-----------------+-----------------+
              |                                   |
       Workload error                     Platform error
              |                                   |
   +----------+----------+         +-------------+-------------+
   |          |          |         |             |             |
  Single   Several    All deps   Auth         Network        Storage
  pod      pods       degraded   (Auth0)      / Ingress      (Postgres
  crashes  CrashLoop                          rate-limited)   / Redis)
   |          |          |         |             |             |
   v          v          v         v             v             v
[A: pod    [B: HPA   [C: drain   [D: jwks    [E: ingress    [F: stateful
 logs]      thrash]   the queue]  503]        503]           failover]
```

## Common diagnostic commands

```powershell
# Pod status across both AQP namespaces
kubectl get pods -n aqp -o wide
kubectl get pods -n aqp-admin -o wide

# Top resource consumers
kubectl top pods -n aqp --sort-by=cpu
kubectl top pods -n aqp --sort-by=memory

# Recent events
kubectl get events -n aqp --sort-by='.lastTimestamp' | tail -n 30

# Tail logs for the API
kubectl logs -n aqp deploy/aqp-core --tail=200 -f

# Control-plane audit log (rolled to stdout by default; if AQP_CP_AUDIT_LOG_PATH
# is set, also written to a file).
kubectl logs -n aqp-admin deploy/aqp-cp --tail=200 -f | findstr workload_run

# Recent terraform_runs (provisioning audit ledger).
kubectl exec -n aqp deploy/aqp-core -- python -m aqp.cli runs list --limit 20
```

## Scenario A — single pod crashes

```powershell
# Identify the crashing pod
kubectl get pods -n aqp -l app=aqp-core | findstr CrashLoop

# Inspect
kubectl describe pod -n aqp <pod-name>
kubectl logs -n aqp <pod-name> --previous

# Rolling restart of the deployment (HPA + PDB keep the service up)
kubectl rollout restart -n aqp deployment/aqp-core
```

## Scenario B — HPA thrashing

The HPA is scaling rapidly up + down, never stabilising.

```powershell
# Check the HPA's recent decisions
kubectl describe hpa -n aqp aqp-core

# Most common cause: a runaway query or backtest that spikes CPU then
# crashes back. Check the audit log for recent task starts.
kubectl logs -n aqp deploy/aqp-worker --tail=500 | findstr "started\|finished\|FAILED"

# Mitigation: temporarily widen the HPA stabilizationWindow.
kubectl patch hpa -n aqp aqp-core --type='json' -p='[
  {"op":"replace","path":"/spec/behavior/scaleUp/stabilizationWindowSeconds","value":300}
]'
```

## Scenario C — Celery queue depth alarm

```powershell
# Drain the queue from the worker side
kubectl exec -n aqp deploy/aqp-worker -- celery -A aqp.tasks.celery_app inspect active

# Scale workers up
kubectl scale -n aqp deployment/aqp-worker --replicas=8

# Or via the control plane (lands an audit row)
curl -X PATCH https://manage.aqp.enterprise.com/manage/deployments/aqp-worker/scale?replicas=8 `
  -H "Authorization: Bearer $TOKEN"
```

## Scenario D — Auth0 JWKS returns 503

Symptom: every authenticated request fails with `jwks_unreachable`.

```powershell
# Probe JWKS directly from inside a pod
kubectl exec -n aqp deploy/aqp-core -- curl -fsS https://your-tenant.us.auth0.com/.well-known/jwks.json

# Common causes:
# - Auth0 service incident (https://status.auth0.com/)
# - Outbound 443 blocked by NetworkPolicy (check network-policies.yaml)
# - DNS resolution failure inside the cluster

# Mitigation: flip AQP_AUTH_ENFORCE to permissive for read-only routes
# while you wait for Auth0 to recover. ONLY do this if your operator
# UI is firewalled at the Ingress layer.
kubectl set env -n aqp deploy/aqp-core AQP_AUTH_ENFORCE=permissive
```

## Scenario E — Ingress returns 503

```powershell
# Check NGINX Ingress controller
kubectl -n ingress-nginx get pods
kubectl -n ingress-nginx logs deploy/ingress-nginx-controller --tail=200

# Check service endpoints
kubectl get endpoints -n aqp aqp-client
kubectl get endpoints -n aqp-admin aqp-cp

# If endpoints are empty, the pods aren't passing readinessProbe.
```

## Scenario F — Stateful service failover

### Postgres

The compose stack uses a single Postgres pod backed by a PVC. K8s overlays should be migrated to a managed Postgres (Aurora / Cloud SQL / Azure Database for PostgreSQL) before going to prod.

For dev/staging:
```powershell
kubectl -n aqp delete pod -l app=postgres   # restarts; data persists in PVC
```

### Redis Stack

```powershell
kubectl -n aqp delete pod redis-master-0   # StatefulSet brings it back
```

## Post-incident

1. Open an incident report in `aqp_docs/incidents/<yyyy-mm-dd>-<slug>.md`.
2. Capture: timeline, blast radius, root cause, fixes applied, follow-ups.
3. If a hard rule was bypassed (e.g. AQP_AUTH_ENFORCE flipped to permissive), schedule the revert as a P1 task.
4. Add a regression test to prevent the same class of incident.
