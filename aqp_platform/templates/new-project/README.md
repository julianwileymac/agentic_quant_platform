# New Project Template

Template for deploying a new service on the RPi Kubernetes cluster framework. Copy this folder, replace the placeholders, and register the service in the root Kustomization.

## Quick Start

```bash
# 1. Copy the template into base-services (or observability / mlops as appropriate)
cp -r templates/new-project/kubernetes kubernetes/base-services/my-app

# 2. Replace all placeholders (see table below)
#    On Linux/macOS:
find kubernetes/base-services/my-app -type f -name '*.yaml' \
  -exec sed -i 's/__APP_NAME__/my-app/g; s/__APP_NAMESPACE__/data-services/g; s/__APP_IMAGE__/myregistry\/my-app:v1.0.0/g; s/__APP_PORT__/8080/g; s/__APP_HOST__/my-app.local/g; s/__APP_DATA_PATH__/\/data/g; s/__APP_COMPONENT__/backend/g' {} +

# 3. Add the service to the root kustomization
#    Edit kubernetes/kustomization.yaml and add under resources:
#      - base-services/my-app/

# 4. (Optional) Add a new namespace if needed
#    Edit kubernetes/namespaces/namespaces.yaml

# 5. Deploy
kubectl apply -k kubernetes/
```

## Placeholders

Find and replace these values across all YAML files in the `kubernetes/` directory.

| Placeholder | Description | Example |
|---|---|---|
| `__APP_NAME__` | Service name (lowercase, hyphenated) | `my-app` |
| `__APP_NAMESPACE__` | Target Kubernetes namespace | `data-services` |
| `__APP_IMAGE__` | Container image with tag | `myregistry/my-app:v1.0.0` |
| `__APP_PORT__` | Primary container port (integer) | `8080` |
| `__APP_HOST__` | Ingress hostname | `my-app.local` |
| `__APP_DATA_PATH__` | Container mount path for persistent data | `/data` |
| `__APP_COMPONENT__` | Kustomize component label | `backend`, `database`, `api` |

## Files Included

| File | Purpose | Optional? |
|---|---|---|
| `kustomization.yaml` | Kustomize config, namespace, labels | No |
| `deployment.yaml` | Deployment with probes, resources, affinity | No |
| `service.yaml` | ClusterIP + LoadBalancer services | No |
| `ingress.yaml` | nginx Ingress for `*.local` access | Yes |
| `configmap.yaml` | Non-sensitive environment variables | Yes |
| `secret.yaml` | Sensitive credentials | Yes |
| `pvc.yaml` | Persistent storage (local-path) | Yes |

### Removing Optional Files

If your service doesn't need a file (e.g., stateless services don't need `pvc.yaml`):

1. Delete the file from the service directory.
2. Remove the filename from the `resources` list in `kustomization.yaml`.
3. Remove any references in `deployment.yaml`:
   - **No PVC**: Remove the `volumes` and `volumeMounts` sections.
   - **No ConfigMap**: Remove the `configMapRef` entry under `envFrom`.
   - **No Secret**: Remove the `secretRef` entry under `envFrom`.

## Available Namespaces

| Namespace | Purpose |
|---|---|
| `data-services` | Storage and databases |
| `ml-platform` | ML runtimes and tracking |
| `observability` | Monitoring and tracing |
| `development` | Development tools |
| `management` | Cluster management |
| `mlops` | MLOps and workflows |
| `ingress` | Ingress controllers |

To add a new namespace, append to `kubernetes/namespaces/namespaces.yaml`:

```yaml
---
apiVersion: v1
kind: Namespace
metadata:
  name: my-namespace
  labels:
    app.kubernetes.io/managed-by: rpi-k8s-cluster
    purpose: my-purpose
```

## Conventions

- **Labels**: Every resource uses `app: <name>` as the selector label. Kustomize adds `app.kubernetes.io/{name,component,part-of}` automatically.
- **Resource limits**: Always set `requests` and `limits` for CPU and memory.
- **Health probes**: Every Deployment should have `livenessProbe` and `readinessProbe`.
- **Node affinity**: Prefer the control-plane node for single-replica stateful workloads.
- **Service names**: Use `<name>` for ClusterIP and `<name>-external` for LoadBalancer.
- **Ingress hosts**: Follow the `<service>.local` pattern with `ingressClassName: nginx`.
- **PVC naming**: `<service>-data` with `storageClassName: local-path`.
- **Cross-namespace access**: Use `<service>.<namespace>.svc.cluster.local:<port>`.
- **Secrets**: Use `stringData` for readability; change defaults before production.

For more details, see [docs/extending-framework.md](../../docs/extending-framework.md).
