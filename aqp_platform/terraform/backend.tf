###############################################################################
# Root state backend.
#
# This file declares the DEFAULT (``local``) backend used when running
# the root composition directly. Per-environment overrides live under
# ``terraform/environments/<env>/backend.tf`` and tell terraform to
# either:
#
# - Pin to a remote backend (S3 + DynamoDB lock / Azure Storage /
#   GCS / Terraform Cloud) for paper + live.
# - Use a per-tenant local backend file for the ``wiley-tech``
#   sandbox.
#
# The default below is intentionally local so ``terraform plan`` from
# the repo root just works without setting up cloud state first.
###############################################################################

terraform {
  backend "local" {
    path = "../data/terraform/state/root.tfstate"
  }
}
