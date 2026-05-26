package terraform.deny_public_access

# OPA policy — fail any plan that creates a publicly-accessible
# resource without an explicit allowlist annotation.

violation[msg] {
  resource := input.planned_values.root_module.resources[_]
  resource.type == "aws_s3_bucket"
  resource.values.acl == "public-read"
  msg := sprintf("Public S3 bucket forbidden: %s", [resource.address])
}

violation[msg] {
  resource := input.planned_values.root_module.resources[_]
  resource.type == "aws_db_instance"
  resource.values.publicly_accessible == true
  msg := sprintf("Publicly-accessible RDS forbidden: %s", [resource.address])
}

violation[msg] {
  resource := input.planned_values.root_module.resources[_]
  resource.type == "aws_security_group_rule"
  resource.values.cidr_blocks[_] == "0.0.0.0/0"
  resource.values.from_port < 1024
  msg := sprintf(
    "Wide-open security group rule below port 1024: %s",
    [resource.address],
  )
}
