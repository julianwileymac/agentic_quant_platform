# Local-only TF_VAR defaults. Override via -var or TF_VAR_<name>.
#
# Common overrides:
#   app_version    = "v0.1.0"   # tag a build before destroy
#   registry_port  = 5001       # bump if 5001 collides
#   lb_http_port   = 8000       # bump if 8000 collides
environment   = "local"
namespace     = "aqp-local"
cluster_name  = "aqp-local"
app_version   = "latest"
registry_port = 5001
lb_http_port  = 8000
lb_https_port = 3001
# Keep this aligned with configs/deployment/topology.yaml tooling.local_shell.
# Git Bash avoids the WSL bash shim on Windows hosts.
local_shell_interpreter = "C:/Program Files/Git/bin/bash.exe"
enabled_services = [
  "aqp-core",
  "aqp-worker",
  "aqp-beat",
  "aqp-client",
  "postgres",
  "redis",
  "neo4j",
  "chromadb",
  "mlflow",
  "otel-collector",
  "jaeger",
]
