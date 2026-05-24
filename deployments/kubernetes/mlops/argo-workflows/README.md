# Argo Workflows - ML Pipeline Orchestration

Argo Workflows is a Kubernetes-native workflow engine for orchestrating parallel jobs on Kubernetes, perfect for ML training pipelines and data processing workflows.

## Installation

```bash
# Add Argo Helm repository
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update

# Ensure MinIO credentials secret exists
kubectl apply -f secret.yaml

# (Optional) manually create bucket if bootstrap job is not used
kubectl run -it --rm minio-client --image=minio/mc --restart=Never -- \
  sh -c "mc alias set minio http://minio.aqp-data-services.svc.cluster.local:9000 minioadmin minioadmin123 && \
         mc mb --ignore-existing minio/argo-workflows"

# Install or upgrade Argo Workflows
helm upgrade --install argo-workflows argo/argo-workflows \
  --namespace mlops \
  --create-namespace \
  -f values.yaml

# Install Argo Events CRDs/controller to avoid Sensor/EventSource NotFound errors
helm upgrade --install argo-events argo/argo-events \
  --namespace mlops \
  --create-namespace \
  -f ../argo-events/values.yaml

# Create a default EventBus
kubectl apply -k ../argo-events/
```

## Access

After installation, Argo Workflows UI is accessible at:
- **Internal**: `http://argo-workflows-server.mlops:2746`
- **External**: `http://argo.local` (via Ingress)

## Example Workflow: ML Training Pipeline

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: ml-training-
  namespace: mlops
spec:
  entrypoint: train-model
  templates:
    - name: train-model
      dag:
        tasks:
          - name: prepare-data
            template: data-prep
          - name: train
            dependencies: [prepare-data]
            template: train-job
          - name: evaluate
            dependencies: [train]
            template: evaluate-job
    
    - name: data-prep
      container:
        image: python:3.11
        command: [python, -c]
        args: ["print('Preparing data...')"]
        resources:
          requests:
            memory: 1Gi
            cpu: 500m
    
    - name: train-job
      container:
        image: rayproject/ray:2.9.0
        command: [python, -c]
        args: ["print('Training model with Ray...')"]
        resources:
          requests:
            memory: 2Gi
            cpu: 1000m
    
    - name: evaluate-job
      container:
        image: python:3.11
        command: [python, -c]
        args: ["print('Evaluating model...')"]
        resources:
          requests:
            memory: 1Gi
            cpu: 500m
```

## Integration with Ray

Argo Workflows can launch Ray jobs for distributed ML training:

```yaml
- name: ray-training
  container:
    image: rayproject/ray:2.9.0
    command: [ray, submit]
    args:
      - --address=ray-head.ml-platform:10001
      - train_script.py
```

## Integration with MLFlow

Workflows can log experiments to MLFlow:

```yaml
- name: log-to-mlflow
  container:
    image: python:3.11
    env:
      - name: MLFLOW_TRACKING_URI
        value: http://mlflow.ml-platform:5000
    command: [python, -c]
    args:
      - |
        import mlflow
        mlflow.log_param("epochs", 10)
        mlflow.log_metric("accuracy", 0.95)
```

## Artifact Storage

Workflows store artifacts in MinIO. Access artifacts via the Argo UI or MinIO console.

## Packaged Pipeline Templates

Reusable workflow templates and schedules for ingestion, hybrid transforms, vector sync,
and CDC are included under:
`kubernetes/mlops/pipelines/`

Apply them with:

```bash
kubectl apply -k kubernetes/mlops/pipelines/
```

## Monitoring

Argo Workflows exposes Prometheus metrics. The repository includes a ServiceMonitor in
`kubernetes/observability/prometheus/servicemonitors.yaml` to scrape controller metrics.

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: argo-workflows-controller
  namespace: observability
spec:
  namespaceSelector:
    matchNames:
      - mlops
  selector:
    matchLabels:
      app: argo-workflows-controller-metrics
  endpoints:
    - port: metrics
      path: /metrics
      interval: 30s
```

## Troubleshooting Argo API Discovery Errors

If Argo UI/API shows:
`Not Found: the server could not find the requested resource (get sensors.argoproj.io)`

Run:

```bash
kubectl get crd sensors.argoproj.io eventsources.argoproj.io eventbus.argoproj.io
helm status argo-events -n mlops
kubectl get eventbus -n mlops
kubectl rollout restart deployment/argo-workflows-server -n mlops
```
