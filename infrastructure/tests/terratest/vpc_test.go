package test

import (
	"testing"

	"github.com/gruntwork-io/terratest/modules/terraform"
)

// TestVpcModule_PlanOnly runs `terraform init && terraform plan` against
// the vpc module to validate that the HCL parses + every required
// variable is wired correctly. Skips actual AWS API calls — heavy
// integration tests live in `tests/terraform-test/`.
func TestVpcModule_PlanOnly(t *testing.T) {
	t.Parallel()
	options := &terraform.Options{
		TerraformDir: "../../modules/vpc",
		Vars: map[string]interface{}{
			"name": "aqp-test",
			"cidr": "10.99.0.0/16",
		},
		NoColor: true,
	}
	defer terraform.Destroy(t, options)
	terraform.InitAndPlan(t, options)
}
