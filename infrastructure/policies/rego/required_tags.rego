package terraform.required_tags

# OPA policy — every taggable AWS resource must carry these tags.
# Wired into the `terraform-pipeline.yml` plan stage via `conftest`.
# Mirror of the Sentinel policy when running in HCP Terraform.

required_tags := {"managed_by", "env", "repo"}

violation[msg] {
  some resource_type, name
  resource := input.planned_values.root_module.resources[_]
  resource.address != ""
  resource.values.tags
  not has_all_required_tags(resource.values.tags)
  msg := sprintf(
    "%s missing required tags %v",
    [resource.address, missing_tags(resource.values.tags)],
  )
}

has_all_required_tags(tags) {
  every key in required_tags {
    tags[key]
  }
}

missing_tags(tags) := result {
  result := [key | key := required_tags[_]; not tags[key]]
}
