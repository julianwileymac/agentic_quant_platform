output "controller_role_arn" { value = aws_iam_role.karpenter.arn }
output "node_pools" {
  value = ["compute", "gpu", "spot-backtests"]
}
