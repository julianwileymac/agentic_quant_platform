# `modules/alb`

Wraps [`terraform-aws-modules/alb/aws ~> 9.0`](https://registry.terraform.io/modules/terraform-aws-modules/alb/aws/latest)
to provision a public ALB + HTTPS listener with Cognito-gated rules in
front of the ECS Fargate control plane.

## Pairing

| Upstream module               | Wiring                                                                                                                     |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `modules/cognito-userpool`    | Pass `cognito_user_pool_arn`, `cognito_user_pool_client_id`, `cognito_user_pool_domain`.                                   |
| `modules/acm-certificates`    | Pass `certificate_arn` for the HTTPS listener.                                                                             |
| `modules/cloudfront`          | The CloudFront origin is `aws_lb.dns_name` (exported here as `dns_name`).                                                  |
| `modules/ecs-fargate-control-plane` | Pass `target_group_arns["admin"]` + `["agentcore_proxy"]` into each `aws_ecs_service.load_balancer.target_group_arn`. |
