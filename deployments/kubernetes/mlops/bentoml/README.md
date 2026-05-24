# BentoML / Yatai - Model Serving Platform

BentoML is a framework-agnostic tool for packaging and deploying ML models. Yatai is the Kubernetes operator that manages BentoML deployments on Kubernetes.

## Installation

```bash
# Add BentoML Helm repository
helm repo add bentoml https://bentoml.github.io/yatai-chart
helm repo update

# Create PostgreSQL database and user
kubectl exec -it -n data-services deployment/postgresql -- psql -U postgres -c "
  CREATE DATABASE bentoml;
  CREATE USER bentoml WITH PASSWORD 'bentoml123';
  GRANT ALL PRIVILEGES ON DATABASE bentoml TO bentoml;
"

# Create MinIO bucket for artifacts
kubectl run -it --rm minio-client --image=minio/mc --restart=Never -- \
  sh -c "mc alias set minio http://minio.aqp-data-services.svc.cluster.local:9000 minioadmin minioadmin123 && \
         mc mb --ignore-existing minio/bentoml-artifacts"

# Create Kubernetes secrets
kubectl apply -f secret.yaml

# Install or upgrade Yatai
helm upgrade --install yatai bentoml/yatai \
  --namespace ml-platform \
  --create-namespace \
  -f values.yaml \
  --set yatai.minio.external.endpoint="$(kubectl get secret -n ml-platform yatai-minio -o jsonpath='{.data.endpoint}' | base64 -d)" \
  --set yatai.minio.external.accessKey="$(kubectl get secret -n ml-platform yatai-minio -o jsonpath='{.data.accesskey}' | base64 -d)" \
  --set yatai.minio.external.secretKey="$(kubectl get secret -n ml-platform yatai-minio -o jsonpath='{.data.secretkey}' | base64 -d)" \
  --set yatai.minio.external.bucket="$(kubectl get secret -n ml-platform yatai-minio -o jsonpath='{.data.bucket}' | base64 -d)"
```

## Access

After installation, Yatai UI is accessible at:
- **Internal**: `http://yatai.ml-platform:3000`
- **External**: `http://yatai.local` (via Ingress)

## Creating a Bento Service

### 1. Define Your Service

```python
# service.py
import bentoml
from bentoml.io import JSON

@bentoml.service(
    resources={"cpu": "1", "memory": "2Gi"},
    traffic={"timeout": 60}
)
class MyMLService:
    @bentoml.api(input=JSON(), output=JSON())
    def predict(self, input_data):
        # Your model inference logic
        return {"prediction": "result"}
```

### 2. Build and Save Bento

```python
# build_bento.py
import bentoml

# Build the service
svc = MyMLService()

# Save as Bento
bentoml.build("my-ml-service:latest")
```

### 3. Deploy to Kubernetes

```python
# deploy.py
import bentoml

# Deploy using Yatai
yatai_client = bentoml.YataiClient()

deployment = yatai_client.deployment.create(
    name="my-ml-service",
    bento="my-ml-service:latest",
    namespace="ml-platform",
    replicas=2
)
```

## Integration with MLFlow

Deploy models from MLFlow registry:

```python
import mlflow
import bentoml

# Load model from MLFlow
model = mlflow.sklearn.load_model("models:/my-model/Production")

# Create BentoML service
svc = bentoml.sklearn.save_model("my-model", model)

# Deploy
bentoml.deploy("my-model", platform="yatai")
```

## Integration with Ray

BentoML services can use Ray for distributed inference:

```python
import ray
from bentoml.io import JSON

@bentoml.service(
    resources={"cpu": "2", "memory": "4Gi"}
)
class RayMLService:
    @bentoml.api(input=JSON(), output=JSON())
    def predict(self, input_data):
        # Use Ray for distributed processing
        @ray.remote
        def process_chunk(chunk):
            return model.predict(chunk)
        
        results = ray.get([process_chunk.remote(chunk) for chunk in data_chunks])
        return {"predictions": results}
```

## Monitoring

BentoML services expose Prometheus metrics. Create a ServiceMonitor:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: bentoml-services
  namespace: ml-platform
spec:
  selector:
    matchLabels:
      app.kubernetes.io/component: bento-service
  endpoints:
    - port: metrics
      interval: 30s
```

## Artifact Storage

BentoML stores model artifacts in MinIO. Access via MinIO console or S3-compatible API.
