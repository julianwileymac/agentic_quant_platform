# Milvus - Production Vector Database

Milvus is a production-grade, open-source vector database designed to handle billions of vectors with high performance.

## Installation

```bash
# Add Milvus Helm repository
helm repo add milvus https://milvus-io.github.io/milvus-helm
helm repo update

# Ensure MinIO credentials secret exists
kubectl apply -f secret.yaml

# Install or upgrade Milvus
helm upgrade --install milvus milvus/milvus \
  --namespace data-services \
  --create-namespace \
  -f values.yaml \
  --set externalS3.host="$(kubectl get secret -n data-services milvus-minio -o jsonpath='{.data.host}' | base64 -d)" \
  --set externalS3.port="$(kubectl get secret -n data-services milvus-minio -o jsonpath='{.data.port}' | base64 -d)" \
  --set externalS3.accessKey="$(kubectl get secret -n data-services milvus-minio -o jsonpath='{.data.accesskey}' | base64 -d)" \
  --set externalS3.secretKey="$(kubectl get secret -n data-services milvus-minio -o jsonpath='{.data.secretkey}' | base64 -d)" \
  --set externalS3.bucketName="$(kubectl get secret -n data-services milvus-minio -o jsonpath='{.data.bucket}' | base64 -d)"
```

## Configuration

This deployment uses:
- **Standalone Mode**: Appropriate for the RPi cluster size
- **External MinIO**: Uses existing MinIO instance for object storage
- **Embedded etcd**: For metadata storage
- **50GB PVC**: For vector data persistence
- **ServiceMonitor**: Enabled for Prometheus metrics

## Access

After installation, Milvus is accessible at:
- **Internal**: `milvus.data-services:19530`
- **External**: `http://milvus.local` (via Ingress)

## Python Client Example

```python
from pymilvus import connections, Collection

# Connect to Milvus
connections.connect(
    alias="default",
    host="milvus.data-services",
    port="19530"
)

# Create a collection
from pymilvus import CollectionSchema, FieldSchema, DataType

fields = [
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True),
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=128)
]
schema = CollectionSchema(fields, "Example collection")
collection = Collection("example_collection", schema)

# Insert vectors
vectors = [[random.random() for _ in range(128)] for _ in range(1000)]
collection.insert([list(range(1000)), vectors])
collection.flush()

# Search
search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
results = collection.search(
    data=[vectors[0]],
    anns_field="embedding",
    param=search_params,
    limit=10
)
```

## Integration with LangChain

```python
from langchain.vectorstores import Milvus
from langchain.embeddings import HuggingFaceEmbeddings

embeddings = HuggingFaceEmbeddings()
vector_store = Milvus(
    embedding_function=embeddings,
    connection_args={
        "host": "milvus.data-services",
        "port": "19530"
    }
)
```

## Distributed Tracing

Milvus is configured to emit OpenTelemetry traces via OTLP to the cluster's
OTel Collector, which forwards them to Jaeger for storage and querying.

### Trace Pipeline

```
Milvus --OTLP gRPC--> OTel Collector --OTLP--> Jaeger
                                                  |
                                          Jaeger REST API
                                                  |
                                       analyze-traces.py (Windows)
                                                  |
                                          Ollama LLM analysis
```

### Viewing Traces

- **Jaeger UI**: `http://jaeger.local:16686` -- search for service `milvus`
- **Grafana**: Use the Jaeger datasource to explore traces alongside metrics

### LLM-Powered Trace Analysis

From the Windows client (requires Ollama running locally):

```powershell
# One-shot analysis of the last hour
python bootstrap/scripts/analyze-traces.py --lookback 1h

# Ask a specific question
python bootstrap/scripts/analyze-traces.py --lookback 4h -q "Why are inserts slow?"

# Interactive follow-up mode
python bootstrap/scripts/analyze-traces.py --lookback 1h --interactive

# List all services reporting traces
python bootstrap/scripts/analyze-traces.py --list-services
```

### Trace Configuration

Tracing is enabled in `values.yaml` under `config.trace`:

```yaml
config:
  trace:
    exporter: otlp
    sampleFraction: 1.0
    otlp:
      endpoint: otel-collector.observability.svc.cluster.local:4317
      secure: false
```

Set `sampleFraction` to a value less than `1.0` (e.g. `0.1`) in production to
reduce overhead.

## Monitoring

Milvus exposes Prometheus metrics and is automatically scraped by Prometheus via ServiceMonitor. Metrics are available in Grafana.

## Prerequisites

### MinIO Bucket Setup

Before deploying Milvus, ensure the MinIO bucket exists:

```bash
# Option 1: Using kubectl exec (recommended -- no extra tools needed)
kubectl exec -n data-services deploy/minio -- \
  sh -c 'mc alias set local http://localhost:9000 minioadmin minioadmin123 && mc mb local/milvus-bucket --ignore-existing'

# Option 2: Using MinIO client (if installed locally)
mc alias set minio http://minio.aqp-data-services.svc.cluster.local:9000 minioadmin minioadmin123
mc mb minio/milvus-bucket --ignore-existing
```

### Architecture Constraint

Milvus only publishes amd64 Docker images. In a mixed-architecture cluster
(amd64 control plane + ARM64 workers), both the Milvus standalone pod and its
embedded etcd must be scheduled on the amd64 node. The `values.yaml` includes
`nodeSelector` and `tolerations` to enforce this.

## Upgrade / Reinstall

After editing `values.yaml`, apply changes with:

```bash
helm upgrade milvus milvus/milvus \
  --namespace data-services \
  -f values.yaml
```
