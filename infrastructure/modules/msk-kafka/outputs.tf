output "cluster_arn" { value = aws_msk_cluster.this.arn }
output "bootstrap_brokers_sasl_iam" { value = aws_msk_cluster.this.bootstrap_brokers_sasl_iam }
output "zookeeper_connect_string_tls" { value = aws_msk_cluster.this.zookeeper_connect_string_tls }
output "security_group_id" { value = aws_security_group.msk.id }
