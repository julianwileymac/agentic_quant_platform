# `modules/cloudwatch-alarms`

Operator-tier CloudWatch alarms + single-pane-of-glass dashboard.
Every input is optional, so the same module covers everything from
the `envs/minimum` tier (RDS-only) to the full hybrid stack
(RDS + ALB + ECS + Redis + Bedrock).

## Alarm catalog

| Source | Alarm | Default threshold |
| --- | --- | ---: |
| RDS | `CPUUtilization` > X% for 15 min | 80% |
| RDS | `FreeStorageSpace` < X GB | 5 GB |
| ALB | `HTTPCode_Target_5XX_Count` / min | 10 |
| ALB | `UnHealthyHostCount` >= 1 for 3 min | 1 |
| ECS | `RunningTaskCount` < 1 for 5 min | 1 |
| ElastiCache | `EngineCPUUtilization` > X% for 15 min | 80% |
| Bedrock | `InvocationThrottles` > X / 5 min | 10 |

Every alarm posts to the SNS topic passed via `alarm_topic_arn`. When
unset the module creates `<name_prefix>-alarms-<env>` and exports the
ARN via SSM (`/aqp/${env}/alarm_topic_arn`) so the operator can wire
PagerDuty / Slack / email subscriptions out-of-band.

## Dashboard

`aws_cloudwatch_dashboard.main` collates the per-source widgets into
one page named `<name_prefix>-<env>`. Visit the AWS console →
CloudWatch → Dashboards to view it.
