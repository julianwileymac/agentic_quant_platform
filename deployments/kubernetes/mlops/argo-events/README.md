# Argo Events - Event CRDs for Argo Workflows

Argo Workflows can query Argo Events resources (`Sensor` / `EventSource`) in the UI.
If Argo Events CRDs are missing, the UI/API often reports:

`Not Found: the server could not find the requested resource (get sensors.argoproj.io)`

This directory adds a repo-managed install path for Argo Events plus a default EventBus.

## Installation

```bash
# Add/update Argo Helm repo
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update

# Install Argo Events (includes Sensor/EventSource/EventBus CRDs)
helm upgrade --install argo-events argo/argo-events \
  --namespace mlops \
  --create-namespace \
  -f values.yaml

# Create a default EventBus in mlops namespace
kubectl apply -k .
```

## Verification

```bash
# CRDs should exist
kubectl get crd sensors.argoproj.io eventsources.argoproj.io eventbus.argoproj.io

# Controller should be healthy
kubectl get deploy -n mlops argo-events-controller-manager
kubectl logs -n mlops deploy/argo-events-controller-manager --tail=100

# EventBus should be present
kubectl get eventbus -n mlops
```

## Troubleshooting

- If CRDs are still missing, verify Helm release health:
  `helm status argo-events -n mlops`
- If the controller is CrashLoopBackOff, inspect cluster permissions and API aggregation:
  `kubectl describe pod -n mlops -l app.kubernetes.io/name=argo-events`
- If the Argo Workflows UI still shows stale errors, restart the server deployment:
  `kubectl rollout restart deployment/argo-workflows-server -n mlops`
