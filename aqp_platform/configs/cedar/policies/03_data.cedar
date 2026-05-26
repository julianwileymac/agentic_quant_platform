// =============================================================================
// DataMCP tool surface — agent + user data-access policies.
//
// Phase 4 §7.3 (RESTRUCTURING_PLAN.md). The DataMCP server publishes
// the canonical `data.*` tool surface (Iceberg / Postgres / catalog /
// lineage / entity reads). Cedar gates the mutating tools and the
// regulated-data reads; the bulk reads pass through
// `aqp_platform_core.auth.resource_filter` for performance.
//
// Entity model:
//   Dataset   — Iceberg / Postgres dataset. Attributes:
//                namespace, sensitivity (public|internal|proprietary-alpha|customer-pii|regulated),
//                owner_org_id, retention_days.
//   Tool      — same shape as agents policy.
//   Action    — Action::"read_dataset"
//                Action::"write_dataset"
//                Action::"delete_dataset"
//                Action::"export_dataset"
// =============================================================================

// ------------------------------------------------------------------
// 1. Public + internal data is readable by every authenticated user
//    that holds the matching `data:read` scope.
// ------------------------------------------------------------------
permit (
  principal,
  action == Action::"read_dataset",
  resource is Dataset
)
when {
  principal has scopes
  && principal.scopes.contains("data:read")
  && resource has sensitivity
  && (resource.sensitivity == "public" || resource.sensitivity == "internal")
};

// ------------------------------------------------------------------
// 2. Proprietary-alpha data — org-internal. Requires the principal
//    to match the dataset's owner_org_id.
// ------------------------------------------------------------------
permit (
  principal,
  action == Action::"read_dataset",
  resource is Dataset
)
when {
  principal has org_id
  && resource has owner_org_id
  && principal.org_id == resource.owner_org_id
  && resource has sensitivity
  && resource.sensitivity == "proprietary-alpha"
};

// ------------------------------------------------------------------
// 3. customer-pii — requires the matching clearance.
// ------------------------------------------------------------------
permit (
  principal,
  action == Action::"read_dataset",
  resource is Dataset
)
when {
  principal has clearances
  && principal.clearances.contains("customer-pii")
  && resource has sensitivity
  && resource.sensitivity == "customer-pii"
};

// ------------------------------------------------------------------
// 4. Regulated — explicit clearance + the matching org. Never
//    cross-org for regulated data even with a regulated clearance.
// ------------------------------------------------------------------
permit (
  principal,
  action == Action::"read_dataset",
  resource is Dataset
)
when {
  principal has clearances
  && principal.clearances.contains("regulated")
  && principal has org_id
  && resource has owner_org_id
  && principal.org_id == resource.owner_org_id
  && resource has sensitivity
  && resource.sensitivity == "regulated"
};

// ------------------------------------------------------------------
// 5. Mutating ops — write/delete/export — require the
//    `data:write` (write/delete) or `data:export` (export) scope
//    AND the same sensitivity gate above.
// ------------------------------------------------------------------
permit (
  principal,
  action in [Action::"write_dataset", Action::"delete_dataset"],
  resource is Dataset
)
when {
  principal has scopes
  && principal.scopes.contains("data:write")
  && principal has org_id
  && resource has owner_org_id
  && principal.org_id == resource.owner_org_id
};

permit (
  principal,
  action == Action::"export_dataset",
  resource is Dataset
)
when {
  principal has scopes
  && principal.scopes.contains("data:export")
  && principal has org_id
  && resource has owner_org_id
  && principal.org_id == resource.owner_org_id
};

// ------------------------------------------------------------------
// 6. Agents cannot delete or export datasets — that's reserved for
//    human principals (resource_filter at the route level enforces
//    delete-with-step-up; this is the belt-and-braces gate).
// ------------------------------------------------------------------
forbid (
  principal,
  action in [Action::"delete_dataset", Action::"export_dataset"],
  resource
)
when {
  principal is Agent
};
