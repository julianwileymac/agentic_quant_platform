terraform {
  required_providers {
    auth0 = {
      source  = "auth0/auth0"
      version = "~> 1.11"
    }
  }
}

locals {
  # Canonical AQP scope catalogue. The single source of truth is
  # ``aqp/auth/scopes.py::AQPScope`` in the agentic_quant_platform repo;
  # this list MUST stay in sync with ``ALL_AQP_SCOPES``. Adding a new
  # scope here is a no-op until role permissions reference it below
  # and route handlers call ``Depends(require_scope(<scope>))``.
  scopes = [
    # Data plane
    { value = "data:read", description = "Read AQP data and metadata" },
    { value = "data:write", description = "Mutate AQP data through sanctioned APIs" },
    { value = "admin:iceberg", description = "Drop, consolidate, or redefine Iceberg tables" },
    # Infrastructure (ADR 003)
    { value = "read:infrastructure", description = "View deployment status, pods, logs, and non-secret config" },
    { value = "manage:agents", description = "Start, stop, restart, and scale assigned AQP agents and bot workloads" },
    { value = "manage:infrastructure", description = "Deploy and update AQP services and non-secret ConfigMaps within an assigned org" },
    { value = "admin:cluster", description = "Full cluster control and resource-scope bypass for AQP super-admins" },
    # Agents
    { value = "agent:view", description = "Inspect agent specs, runs, and telemetry" },
    { value = "agent:execute", description = "Invoke or schedule a registered AQP agent" },
    { value = "agent:terminate", description = "Halt a running agent or revoke a long-lived spec" },
    # Trading / portfolio
    { value = "trade:read", description = "Inspect paper / live trading sessions, orders, fills, and PnL" },
    { value = "trade:execute", description = "Submit paper-broker or sandbox-broker orders" },
    { value = "trade:live", description = "Submit real-money orders to a connected live broker" },
    # Backtesting
    { value = "backtest:read", description = "Inspect backtest runs and historical metrics" },
    { value = "backtest:create", description = "Submit a new backtest job to the engine fleet" },
    # ML / RL / RAG
    { value = "rag:query", description = "Query the hierarchical RAG corpus" },
    { value = "ml:workbench", description = "Run ML workbench flows (training, evaluation, registry)" },
    { value = "rl:train", description = "Submit RLExperimentSpec runs through RLRuntime" },
    # Deployment lifecycle
    { value = "deploy:run", description = "Run Terraform/Kubernetes deployments" },
    { value = "deploy:halt", description = "Halt AQP deployments and long-running runtimes" },
    # Terraform IaC (rule 42)
    { value = "terraform:plan", description = "Generate a Terraform plan for an AQP stack" },
    { value = "terraform:apply", description = "Apply a Terraform plan against an AQP stack" },
    { value = "terraform:destroy", description = "Destroy an AQP Terraform stack (super-admin only)" },
    { value = "terraform:cancel", description = "Cancel a running Terraform run" },
    # WorkloadRuntime kill-switch (rule 45)
    { value = "workloads:halt", description = "Halt every running workload via the WorkloadRuntime kill-switch" },
    # Tenancy
    { value = "tenancy:invite", description = "Issue tenancy invites for org / team / workspace / project membership" },
    { value = "tenancy:admin", description = "Mutate tenancy state (orgs, teams, memberships)" },
    { value = "scim:write", description = "Provision AQP users and groups through SCIM" },
    # Platform
    { value = "platform:admin", description = "Implicit super-scope: satisfies any other scope check" },
  ]

  # Role -> permission lattice. Mirrors the lattice in
  # ``aqp_platform_core/auth/rbac.py::_ROLE_LATTICE``. Keep them aligned
  # — the test suite at tests/auth/test_scopes.py asserts that every
  # role's set is the same on both sides.
  role_permissions = {
    viewer = [
      "read:infrastructure",
      "data:read",
      "agent:view",
      "trade:read",
      "backtest:read",
      "rag:query",
    ]
    operator = [
      # viewer +
      "read:infrastructure",
      "data:read",
      "agent:view",
      "trade:read",
      "backtest:read",
      "rag:query",
      # operator-only:
      "manage:agents",
      "agent:execute",
      "agent:terminate",
      "backtest:create",
      "ml:workbench",
      "rl:train",
      "trade:execute",
      "deploy:run",
      "deploy:halt",
      "workloads:halt",
    ]
    admin = [
      # operator +
      "read:infrastructure",
      "data:read",
      "agent:view",
      "trade:read",
      "backtest:read",
      "rag:query",
      "manage:agents",
      "agent:execute",
      "agent:terminate",
      "backtest:create",
      "ml:workbench",
      "rl:train",
      "trade:execute",
      "deploy:run",
      "deploy:halt",
      "workloads:halt",
      # admin-only:
      "manage:infrastructure",
      "data:write",
      "admin:iceberg",
      "terraform:plan",
      "terraform:apply",
      "terraform:cancel",
      "tenancy:invite",
    ]
    superadmin = [
      # admin +
      "read:infrastructure",
      "data:read",
      "agent:view",
      "trade:read",
      "backtest:read",
      "rag:query",
      "manage:agents",
      "agent:execute",
      "agent:terminate",
      "backtest:create",
      "ml:workbench",
      "rl:train",
      "trade:execute",
      "deploy:run",
      "deploy:halt",
      "workloads:halt",
      "manage:infrastructure",
      "data:write",
      "admin:iceberg",
      "terraform:plan",
      "terraform:apply",
      "terraform:cancel",
      "tenancy:invite",
      # superadmin-only:
      "admin:cluster",
      "terraform:destroy",
      "tenancy:admin",
      "scim:write",
      "trade:live",
      "platform:admin",
    ]
  }
}

resource "auth0_client" "spa" {
  count           = var.enabled ? 1 : 0
  name            = var.spa_name
  app_type        = "spa"
  oidc_conformant = true

  callbacks                  = var.callback_urls
  allowed_logout_urls        = var.logout_urls
  web_origins                = var.web_origins
  grant_types                = ["authorization_code", "refresh_token"]
  token_endpoint_auth_method = "none"
}

resource "auth0_resource_server" "api" {
  count                                           = var.enabled ? 1 : 0
  name                                            = var.api_name
  identifier                                      = var.api_identifier
  token_lifetime                                  = 86400
  enforce_policies                                = true
  skip_consent_for_verifiable_first_party_clients = true

  dynamic "scopes" {
    for_each = local.scopes
    content {
      value       = scopes.value.value
      description = scopes.value.description
    }
  }
}

resource "auth0_client" "m2m" {
  count           = var.enabled ? 1 : 0
  name            = "AQP SCIM + Auth0 Sync M2M"
  app_type        = "non_interactive"
  oidc_conformant = true
  grant_types     = ["client_credentials"]
}

resource "auth0_client_grant" "m2m_api" {
  count     = var.enabled ? 1 : 0
  client_id = auth0_client.m2m[0].client_id
  audience  = auth0_resource_server.api[0].identifier
  scopes = [
    "read:infrastructure",
    "manage:infrastructure",
    "data:read",
    "scim:write",
    "deploy:run",
    "deploy:halt",
  ]
}

resource "auth0_role" "viewer" {
  count       = var.enabled ? 1 : 0
  name        = "aqp-viewer"
  description = "Read-only AQP operator for assigned resources"
}

resource "auth0_role" "operator" {
  count       = var.enabled ? 1 : 0
  name        = "aqp-operator"
  description = "AQP operator allowed to manage assigned agents and bot workloads"
}

resource "auth0_role" "admin" {
  count       = var.enabled ? 1 : 0
  name        = "aqp-admin"
  description = "AQP administrator for assigned organization infrastructure"
}

resource "auth0_role" "superadmin" {
  count       = var.enabled ? 1 : 0
  name        = "aqp-superadmin"
  description = "AQP cluster super-admin with admin:cluster scope"
}

resource "auth0_role_permissions" "viewer" {
  count   = var.enabled ? 1 : 0
  role_id = auth0_role.viewer[0].id

  dynamic "permissions" {
    for_each = local.role_permissions.viewer
    content {
      name                       = permissions.value
      resource_server_identifier = auth0_resource_server.api[0].identifier
    }
  }
}

resource "auth0_role_permissions" "operator" {
  count   = var.enabled ? 1 : 0
  role_id = auth0_role.operator[0].id

  dynamic "permissions" {
    for_each = local.role_permissions.operator
    content {
      name                       = permissions.value
      resource_server_identifier = auth0_resource_server.api[0].identifier
    }
  }
}

resource "auth0_role_permissions" "admin" {
  count   = var.enabled ? 1 : 0
  role_id = auth0_role.admin[0].id

  dynamic "permissions" {
    for_each = local.role_permissions.admin
    content {
      name                       = permissions.value
      resource_server_identifier = auth0_resource_server.api[0].identifier
    }
  }
}

resource "auth0_role_permissions" "superadmin" {
  count   = var.enabled ? 1 : 0
  role_id = auth0_role.superadmin[0].id

  dynamic "permissions" {
    for_each = local.role_permissions.superadmin
    content {
      name                       = permissions.value
      resource_server_identifier = auth0_resource_server.api[0].identifier
    }
  }
}

resource "auth0_action" "post_login_claims" {
  count   = var.enabled && var.auth0_sync_url != "" ? 1 : 0
  name    = "AQP post-login claims sync"
  runtime = "node22"
  deploy  = true

  supported_triggers {
    id      = "post-login"
    version = "v3"
  }

  code = templatefile("${path.module}/post_login_action.js.tftpl", {
    sync_url         = var.auth0_sync_url
    api_audience     = var.api_identifier
    claims_namespace = var.claims_namespace
  })
}
