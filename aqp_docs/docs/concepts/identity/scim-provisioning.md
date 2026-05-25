---
title: 'SCIM Provisioning'
summary: 'Enable SCIM with:'
owner: identity-team
last_reviewed: 2026-05-25
audience: both
---

# SCIM Provisioning

AQP exposes a SCIM 2.0 provisioning surface at `/scim/v2/*` for Auth0
Actions or scheduled Auth0 jobs.

## Security

Enable SCIM with:

```bash
AQP_AUTH_SCIM_ENABLED=true
AQP_AUTH_PROVIDER=auth0
AQP_AUTH_REQUIRED=true
```

Authentication is Bearer-only. AQP accepts either:

- a JWT validated against the configured OIDC issuer with audience
  `AQP_AUTH_SCIM_M2M_AUDIENCE` (or `AQP_AUTH_M2M_AUDIENCE`), or
- a long random static token whose SHA-256 digest is stored in
  `AQP_AUTH_SCIM_BEARER_TOKEN_HASH`.

Do not store the raw token in the repository.

## Resource Mapping

- SCIM `User` maps to `users`.
- SCIM `Group` maps to `teams`.
- SCIM `Group.members` maps to `memberships` with `scope_kind="team"`.

Create, patch, replace, deactivate, and group membership operations emit
security audit events through `aqp.auth.audit.emit_audit_event`.

## Auth0 Integration

The `aqp_platform/terraform/modules/auth0_identity` module creates:

- the AQP SPA application,
- the AQP API audience and scopes,
- an M2M client grant for SCIM and Auth0 sync,
- default `aqp-viewer` and `aqp-admin` roles,
- a post-login Action that calls `/_internal/auth0/sync` and injects AQP
  tenancy claims.

For direct enterprise SCIM, point the upstream IdP or Auth0 automation at
`https://<aqp-host>/scim/v2`.
