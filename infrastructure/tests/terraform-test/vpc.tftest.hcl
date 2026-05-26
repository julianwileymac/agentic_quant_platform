# Native `terraform test` framework.
# Verifies the vpc module emits the expected outputs.

variables {
  name = "aqp-test"
  cidr = "10.99.0.0/16"
}

run "plan" {
  command = plan
  module {
    source = "../../modules/vpc"
  }
  assert {
    condition     = output.vpc_cidr == "10.99.0.0/16"
    error_message = "vpc_cidr must round-trip the input"
  }
  assert {
    condition     = length(output.private_subnet_ids) == 3
    error_message = "private_subnet_ids must have one entry per AZ (default 3)"
  }
}
