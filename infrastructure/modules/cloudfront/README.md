# `modules/cloudfront`

CloudFront distribution in front of `modules/alb` for the AWS-native
admin + AgentCore surfaces. The public marketing site at `aqp.fund`
stays on Cloudflare (see `.cursor/rules/cloudflare-edge.mdc`).

## Origin secret

A `var.origin_secret_header_value` header (`X-CloudFront-Secret`) is
injected into every origin request; the ALB listener-rule library
should reject direct hits whose header does not match. Rotate via:

```bash
aws ssm put-parameter \
  --name /aqp/${env}/cloudfront_origin_secret \
  --value $(openssl rand -hex 32) \
  --type SecureString --overwrite
```

then re-apply this module.

## Wiring contract

| SSM parameter                                | Purpose                              |
| -------------------------------------------- | ------------------------------------ |
| `/aqp/${env}/cloudfront_domain`              | CNAME target for the alias records. |
| `/aqp/${env}/cloudfront_distribution_id`     | Invalidation handle for CI.         |
