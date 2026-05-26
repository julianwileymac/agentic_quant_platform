# `modules/cognito-userpool`

End-user Cognito User Pool + the shared SPA app client. Per-tenant app
clients are NOT created here — they are emitted by the rule-42 tenant
namespace bundle (`aqp_cp.terraform.builders.manifests`) so each tenant
gets its own `client_id` for ALB listener-rule isolation.

## Wiring contract

| SSM parameter                                    | Backed type    |
| ------------------------------------------------ | -------------- |
| `/aqp/${env}/cognito_user_pool_id`               | `String`       |
| `/aqp/${env}/cognito_user_pool_arn`              | `String`       |
| `/aqp/${env}/cognito_user_pool_endpoint`         | `String`       |
| `/aqp/${env}/cognito_user_pool_domain`           | `String`       |
| `/aqp/${env}/cognito_shared_client_id`           | `String`       |
| `/aqp/${env}/cognito_shared_client_secret`       | `SecureString` |
