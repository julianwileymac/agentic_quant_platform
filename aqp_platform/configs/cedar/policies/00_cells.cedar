// =============================================================================
// Cell-management policies.
//
// Phase 4 §7.3 (RESTRUCTURING_PLAN.md). These policies gate the
// `/manage/cells/*` mutations exposed by `aqp_control_plane`. Reads
// (`GET /manage/cells`) still go through `require_scope("read:topology")`
// which is faster and Cedar-redundant on the high-throughput path.
//
// Entity model:
//   User      — JWT principal. Attributes: org_id, workspace_id,
//                roles[], scopes[], clearances[].
//   Cell      — deployment cell. Attributes: tier, region,
//                tenancy_strategy, data_classification, tenant_org_id?
//   Action    — verb. The cells router uses:
//                Action::"manage_cell"
//                Action::"register_cell"
//                Action::"update_cell_state"
//                Action::"decommission_cell"
//                Action::"place_tenant_in_cell"
//                Action::"migrate_tenant_to_cell"
// =============================================================================

// ------------------------------------------------------------------
// 1. Cell operators may register + modify cells in their own org.
// ------------------------------------------------------------------
permit (
  principal,
  action in [
    Action::"register_cell",
    Action::"update_cell_state",
    Action::"place_tenant_in_cell",
    Action::"migrate_tenant_to_cell"
  ],
  resource
)
when {
  principal has roles
  && principal.roles.contains("cell_operator")
};

// ------------------------------------------------------------------
// 2. Platform admins may do anything to any cell.
// ------------------------------------------------------------------
permit (
  principal,
  action,
  resource
)
when {
  principal has roles
  && principal.roles.contains("platform_admin")
};

// ------------------------------------------------------------------
// 3. Decommissioning a cell requires the elevated "cell_decom" role
//    AND the principal must hold the matching org_id (cells belong
//    to the org that registered them).
// ------------------------------------------------------------------
permit (
  principal,
  action == Action::"decommission_cell",
  resource
)
when {
  principal has roles
  && principal.roles.contains("cell_decom")
};

// ------------------------------------------------------------------
// 4. Regulated data classification — silo-reg cells holding
//    customer-pii or regulated workloads require the matching
//    clearance. This is the §7.3 example from the plan.
// ------------------------------------------------------------------
forbid (
  principal,
  action,
  resource
)
when {
  resource has data_classification
  && resource.data_classification == "regulated"
  && (!(principal has clearances) || !principal.clearances.contains("regulated"))
};

forbid (
  principal,
  action,
  resource
)
when {
  resource has data_classification
  && resource.data_classification == "customer-pii"
  && (!(principal has clearances) || !principal.clearances.contains("customer-pii"))
};
