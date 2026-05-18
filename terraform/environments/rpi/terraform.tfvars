# Override these for the live rpi_kubernetes cluster before apply.
rpi_kubeconfig_path = "~/.kube/config"
rpi_kube_context    = ""
rpi_namespace       = "aqp"
app_version         = "replace-with-immutable-tag"
rpi_image_registry  = "ghcr.io/julianwiley"
rpi_ingress_host    = ""
auth0_domain        = ""
auth0_audience      = "https://aqp/api"
auth0_client_id     = ""
enabled_services = [
  "aqp-api",
  "aqp-worker",
  "aqp-beat",
  "aqp-frontend",
  "postgres",
  "redis",
  "neo4j",
  "chromadb",
  "mlflow",
  "otel-collector",
  "jaeger",
]
