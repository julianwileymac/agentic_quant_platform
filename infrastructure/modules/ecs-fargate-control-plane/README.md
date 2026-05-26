# `modules/ecs-fargate-control-plane`

ECS Fargate cluster + per-service task definitions for the AWS-native
admin BFF (`aqp-admin`) and the AgentCore reverse proxy
(`aqp-agentcore-proxy`).

The EKS Karpenter foundation continues to host the quant runtime
workloads (Celery workers, Iceberg writers, MLflow, Strimzi, Flink)
per the hybrid topology decision; this module is the Fargate slice
only.

## ADOT sidecar

Every task ships an `aws-observability/aws-otel-collector` sidecar.
The application emits OTLP traces / metrics to `localhost:4317` per
AGENTS rule 4; the sidecar fans out to X-Ray + CloudWatch
Application Signals + CloudWatch Metrics.

## ECS Exec

`enable_execute_command = true` is set on every service so the
`AwsProvider.exec` method can dispatch SSM Session Manager exec
calls. The corresponding IAM permissions are wired into the task
role automatically.

## Wiring contract

| SSM parameter                                | Purpose                                                |
| -------------------------------------------- | ------------------------------------------------------ |
| `/aqp/${env}/ecs_cluster_name`               | Read by `AwsProvider._scale_sync` / `_status_sync`.    |
| `/aqp/${env}/ecs_cluster_arn`                | Read by the audit ledger + CloudFormation drift checks.|
| `/aqp/${env}/ecs_service_names`              | `StringList` of every service the cluster runs.        |
