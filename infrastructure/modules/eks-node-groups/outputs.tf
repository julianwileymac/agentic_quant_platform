output "general_node_group_arn" { value = aws_eks_node_group.general.arn }
output "general_node_role_arn" { value = aws_iam_role.node.arn }
